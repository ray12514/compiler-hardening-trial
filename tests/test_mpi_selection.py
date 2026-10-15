"""Check that a passing diagnostic can configure component selection without CPU sharing."""

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_mpi_driver import REPO

with patch.object(sys, "path", [str(REPO / "scripts"), *sys.path]):
    spec = importlib.util.spec_from_file_location("apply_startup", REPO / "scripts/apply_mpi_startup_selection.py")
    selection = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(selection)


class SelectionTests(unittest.TestCase):
    def fixture(self, root):
        (root / "runner/state").mkdir(parents=True)
        (root / "runner/state/fftw-full.json").write_text("retain existing artifacts")
        (root / "env.sh").write_text("unset UCX_TLS UCX_NET_DEVICES\n"
            "unset OMPI_MCA_rmaps_base_oversubscribe OMPI_MCA_hwloc_base_binding_policy\n")
        previous = root / "runner/rdma.sh"
        previous.write_text("export UCX_TLS=rc,sm,self\n")
        config = {"ucx_configure_args": ["--with-verbs", "--with-rdmacm"],
                  "tuning_file": str(previous), "recovery_manifest": "preserve this selection"}
        (root / "runner/mpi-config.json").write_text(json.dumps(config))
        for arm, file in (("full", "mpi-env.sh"), ("reference", "mpi-env-reference.sh")):
            (root / file).write_text(f'source "$TRIAL_ROOT/env.sh"\n'
                f'export MPI_PREFIX="{root}/{arm}-mpi" UCX_PREFIX="{root}/{arm}-ucx"\n')
        report = root / "results/diagnostics/mpi-startup-example/report.json"
        report.parent.mkdir(parents=True)
        report.write_text(json.dumps({"passed": True, "mode": "no-openib-ofi", "arm": "full",
            "mpi_prefix": str(root / "full-mpi"), "oversubscribe": True,
            "runtime_settings": {"UCX_TLS": "rc,sm,self"},
            "startup": {"command": ["mpirun", "--oversubscribe", "--bind-to", "none"]}}))
        return report, previous, config

    def test_preserves_builds_and_fabric_settings_and_applies_components_to_both_arms(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            report, previous, config = self.fixture(root)
            with contextlib.redirect_stdout(io.StringIO()):
                tuning = selection.apply(root)
            saved = json.loads((root / "runner/mpi-config.json").read_text())
            self.assertEqual(saved["ucx_configure_args"], config["ucx_configure_args"])
            self.assertEqual(saved["recovery_manifest"], config["recovery_manifest"])
            self.assertNotIn("oversubscribe", tuning.read_text())
            self.assertNotIn("binding_policy", tuning.read_text())
            self.assertEqual(previous.read_text(), "export UCX_TLS=rc,sm,self\n")
            self.assertEqual((root / "runner/state/fftw-full.json").read_text(), "retain existing artifacts")
            for arm in ("full", "reference"):
                env, note = selection.activated_env(root, arm)
                self.assertIsNotNone(env, note)
                self.assertEqual(env["OMPI_MCA_pml"], "ucx")
                self.assertEqual(env["OMPI_MCA_btl"], "^uct,openib,ofi")
                self.assertEqual(env["OMPI_MCA_mtl"], "^ofi")
                self.assertEqual(env["UCX_TLS"], "rc,sm,self")
                self.assertNotIn("OMPI_MCA_rmaps_base_oversubscribe", env)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(selection.apply(root), tuning)
            self.assertEqual(len(list((root / "runner").glob("mpi-startup-selection-*.sh"))), 1)

    def test_failed_or_mismatched_probe_is_rejected_without_config_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            report, previous, config = self.fixture(root)
            original = (root / "runner/mpi-config.json").read_bytes()
            data = json.loads(report.read_text())
            data["passed"] = False
            report.write_text(json.dumps(data))
            with self.assertRaisesRegex(RuntimeError, "did not pass"):
                selection.apply(root)
            data.update(passed=True, mpi_prefix="/a/different/mpi")
            report.write_text(json.dumps(data))
            with self.assertRaisesRegex(RuntimeError, "different MPI prefix"):
                selection.apply(root)
            self.assertEqual((root / "runner/mpi-config.json").read_bytes(), original)
            self.assertEqual(list((root / "runner").glob("mpi-startup-selection-*.sh")), [])

    def test_config_write_failure_keeps_previous_runtime_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            report, previous, config = self.fixture(root)
            original = (root / "runner/mpi-config.json").read_bytes()
            real_write = selection.atomic_write

            def fail_config(path, text):
                if path.name == "mpi-config.json":
                    raise OSError("injected write failure")
                real_write(path, text)

            with patch.object(selection, "atomic_write", side_effect=fail_config), self.assertRaises(OSError):
                selection.apply(root)
            self.assertEqual((root / "runner/mpi-config.json").read_bytes(), original)
            self.assertTrue(previous.is_file())
            self.assertEqual(list((root / "runner").glob("mpi-startup-selection-*.sh")), [])


if __name__ == "__main__":
    unittest.main()
