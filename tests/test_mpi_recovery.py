"""Check MPI graph retirement and preservation using real driver state files."""

import importlib.util
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch

from test_mpi_driver import REPO, driver_at, executable


def script(name):
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


recovery = script("recover_mpi_rdma")
installer = script("install_driver")


class RecoveryTests(unittest.TestCase):
    def fixture(self, root):
        driver = driver_at(root)
        (root / "build").mkdir()
        (root / "env.sh").write_text("export CC=/usr/bin/gcc\n")
        qualification = {"policy": {"disabled": {}, "events": []}}
        driver.save(driver.HERE / "qualification.json", qualification)
        driver.save(driver.HERE / "setup.json", {
            "qualification": qualification, "env": driver.filehash(root / "env.sh"), "site_env": None,
            "profile_recipe": driver.digest(driver.block("01-common", 0)),
            "measurement_recipes": driver.measurement_hash(),
        })
        for package in ("fftw", "ucx", "openmpi", "fftw-mpi"):
            build, prefix = driver.paths(package, "full")
            build.mkdir(parents=True)
            prefix.mkdir(parents=True)
            artifact = prefix / "library"
            artifact.write_text("original " + package)
            driver.save(driver.HERE / "state" / f"{package}-full.json", {
                "identity": package + "-old", "effective_profile": qualification,
                "artifacts": {str(artifact.relative_to(root)): driver.filehash(artifact)},
            })
        (root / "results").mkdir()
        (root / "results/original.json").write_text('{"old-result":true}')
        return driver

    def test_preserves_serial_and_results_and_archives_complete_mpi_graph(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            driver = self.fixture(root)
            for package in recovery.PACKAGES:
                build, prefix = driver.paths(package, "reference")
                build.mkdir(parents=True)
                prefix.mkdir(parents=True)
                (prefix / "partial-progress").write_text(package)
                driver.save(driver.HERE / "pending" / f"{package}-reference.json", {"interrupted": True})
            (root / "bench").mkdir()
            (root / "bench/fftw-mpi-reference").write_text("caller")
            (root / "mpi-env-reference.sh").write_text("old activation")
            state = (root / "runner/state/fftw-full.json").read_bytes()
            paths = recovery.recovery_plan(driver)
            archive = recovery.retire(driver, paths, ["--with-verbs", "--with-rdmacm"])
            self.assertEqual((root / "runner/state/fftw-full.json").read_bytes(), state)
            self.assertEqual((root / "results/original.json").read_text(), '{"old-result":true}')
            self.assertEqual((root / "install/fftw/full/library").read_text(), "original fftw")
            for package in ("ucx", "openmpi", "fftw-mpi"):
                build, prefix = driver.paths(package, "full")
                self.assertFalse(prefix.exists())
                self.assertTrue((archive / prefix.relative_to(root) / "library").is_file())
                self.assertFalse((driver.HERE / "state" / f"{package}-full.json").exists())
            config = driver.read(driver.HERE / "mpi-config.json")
            self.assertEqual(config["ucx_configure_args"], ["--with-verbs", "--with-rdmacm"])
            self.assertIn("UCX_TLS=rc,sm,self", Path(config["tuning_file"]).read_text())
            self.assertEqual(driver.read(archive / "recovery.json")["status"], "retired")
            for package in recovery.PACKAGES:
                build, prefix = driver.paths(package, "reference")
                self.assertFalse(prefix.exists())
                self.assertTrue((archive / prefix.relative_to(root) / "partial-progress").is_file())
                self.assertFalse((driver.HERE / "pending" / f"{package}-reference.json").exists())
            self.assertTrue((archive / "bench/fftw-mpi-reference").is_file())
            self.assertTrue((archive / "mpi-env-reference.sh").is_file())
            driver.require_setup()

    def test_symlinked_archive_is_rejected_before_moves(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            driver = self.fixture(root)
            target = root / "other-archive"
            target.mkdir()
            (root / "build/retired").symlink_to(target, target_is_directory=True)
            with self.assertRaisesRegex(RuntimeError, "symlinked or external"):
                recovery.recovery_plan(driver)
            self.assertTrue((root / "install/ucx-1.16.0-fixed/library").exists())
            self.assertEqual(list(target.iterdir()), [])

    def test_failed_retirement_rolls_back_every_moved_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            driver = self.fixture(root)
            paths = recovery.recovery_plan(driver)
            before = {p: p.read_bytes() for p in paths if p.is_file()}
            original = Path.rename
            calls = 0

            def fail_once(path, target):
                nonlocal calls
                calls += 1
                if calls == 3:
                    raise OSError("injected storage error")
                return original(path, target)

            with patch.object(Path, "rename", fail_once), self.assertRaises(OSError):
                recovery.retire(driver, paths, ["--with-verbs", "--with-rdmacm"])
            self.assertTrue(all(p.exists() for p in paths))
            self.assertEqual({p: p.read_bytes() for p in before}, before)
            self.assertFalse((driver.HERE / "mpi-config.json").exists())
            manifest = next((root / "build/retired").glob("*/recovery.json"))
            self.assertEqual(driver.read(manifest)["status"], "rolled-back")

    def test_unmanaged_and_modified_installations_are_rejected_before_moves(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            driver = self.fixture(root)
            (root / "install/ucx-1.16.0-fixed/library").write_text("modified")
            with self.assertRaisesRegex(RuntimeError, "Artifact changed"):
                recovery.recovery_plan(driver)
            (driver.HERE / "state/ucx-full.json").unlink()
            with self.assertRaisesRegex(RuntimeError, "Unmanaged ucx-full"):
                recovery.recovery_plan(driver)
            self.assertFalse((root / "build/retired").exists())

    def test_installer_keeps_existing_state_and_saved_rdma_choice(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            driver = self.fixture(root)
            config = driver.HERE / "mpi-config.json"
            config.write_text('{"ucx_configure_args":["--with-verbs","--with-rdmacm"]}')
            before = (driver.HERE / "state/fftw-full.json").read_bytes()
            installer.install(root, REPO)
            self.assertEqual((driver.HERE / "state/fftw-full.json").read_bytes(), before)
            self.assertIn("--with-verbs", config.read_text())
            self.assertTrue(os.access(driver.HERE / "trial", os.X_OK))

    def test_rc_capability_gate_rejects_tcp_only_even_when_configure_requested_verbs(self):
        with tempfile.TemporaryDirectory() as tmp:
            driver = driver_at(Path(tmp))
            with patch.object(driver, "shell", return_value="# Transport: tcp\n# Transport: cma\n"):
                with self.assertRaisesRegex(RuntimeError, "no available RC transport"):
                    driver.verify_ucx_rdma(Path(tmp) / "ucx")
            with patch.object(driver, "shell", return_value="# Transport: rc_mlx5\n# Device: mlx5_0:1\n"):
                self.assertIn("rc_mlx5", driver.verify_ucx_rdma(Path(tmp) / "ucx"))

    def test_failed_prerequisites_do_not_retire_the_existing_graph(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            driver = self.fixture(root)
            with patch.object(sys, "argv", ["recover", "--trial-root", str(root), "--apply"]), \
                 patch.dict(os.environ, {"SLURM_JOB_ID": "123", "TRIAL_UCX_CONFIGURE_ARGS": "--with-verbs --with-rdmacm"}), \
                 patch.object(recovery, "load_driver", return_value=driver), \
                 patch.object(driver, "verify_mpi_archives"), \
                 patch.object(recovery, "check_prerequisites", side_effect=RuntimeError("missing headers")), \
                 contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()), \
                 self.assertRaises(SystemExit):
                recovery.main()
            self.assertTrue((root / "install/ucx-1.16.0-fixed/library").exists())
            self.assertTrue((driver.HERE / "state/ucx-full.json").exists())
            self.assertFalse((root / "build/retired").exists())

    def test_unfinished_recovery_blocks_another_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            driver = self.fixture(root)
            manifest = root / "build/retired/mpi-rdma-previous/recovery.json"
            driver.save(manifest, {"status": "retiring"})
            with self.assertRaisesRegex(RuntimeError, "Unfinished prior recovery"):
                recovery.recovery_plan(driver)

    def test_repeating_successful_recovery_keeps_new_progress(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            driver = self.fixture(root)
            recovery.retire(driver, recovery.recovery_plan(driver), ["--with-verbs", "--with-rdmacm"])
            (root / "build/ucx-fixed").mkdir()
            progress = root / "build/ucx-fixed/new-progress"
            progress.write_text("keep this")
            with patch.object(sys, "argv", ["recover", "--trial-root", str(root), "--apply"]), \
                 patch.dict(os.environ, {"TRIAL_UCX_CONFIGURE_ARGS": "--with-verbs --with-rdmacm"}), \
                 patch.object(recovery, "load_driver", return_value=driver), \
                 contextlib.redirect_stdout(io.StringIO()):
                recovery.main()
            self.assertEqual(progress.read_text(), "keep this")
            self.assertEqual(len(list((root / "build/retired").glob("mpi-rdma-*"))), 1)


if __name__ == "__main__":
    unittest.main()
