"""Local fixture checks; no UCX, fabric, scheduler or MPI installation required."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/collect_mpi_diagnostics.py"
spec = importlib.util.spec_from_file_location("diagnostics", SCRIPT)
diagnostics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostics)


class DiagnosticsTests(unittest.TestCase):
    def executable(self, path, body):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/bin/bash\nset -eu\n" + body)
        path.chmod(0o755)

    def test_collects_both_saved_prefixes_preserves_state_and_does_not_launch_mpi(self):
        with tempfile.TemporaryDirectory(prefix="mpi-diagnostics-") as tmp:
            root = Path(tmp)
            (root / "env.sh").write_text("unset UCX_TLS UCX_NET_DEVICES\n")
            tuning = root / "fabric.sh"
            tuning.write_text("export UCX_TLS=rc,sm,self\nexport UCX_NET_DEVICES=mlx5_2:1\n")
            sentinel = root / "runner/state/ucx-full.json"
            sentinel.parent.mkdir(parents=True)
            sentinel.write_text('{"preserve":true}\n')
            for arm in ("full", "reference"):
                # Discover saved non-default prefixes, not just the fallback paths.
                ucx, mpi = root / f"custom-{arm}-ucx", root / f"custom-{arm}-mpi"
                self.executable(ucx / "bin/ucx_info", """test "$UCX_TLS" = rc,sm,self
test "$UCX_NET_DEVICES" = mlx5_2:1
if test "$1" = -d; then
    printf '# Transport: rc_mlx5\n# Device: mlx5_2:1\n# Transport: posix\n# Device: memory\n'
else
    printf 'UCX 1.16.0 configured --with-verbs --with-rdmacm\n'
fi
""")
                self.executable(mpi / "bin/ompi_info", "echo 'Open MPI 4.1.8 / ucx'\n")
                self.executable(mpi / "bin/mpirun", f"touch '{root / 'MPI_WAS_LAUNCHED'}'\nexit 99\n")
                activation = root / ("mpi-env.sh" if arm == "full" else "mpi-env-reference.sh")
                activation.write_text(
                    f"source '{root / 'env.sh'}'\n"
                    f"export MPI_PREFIX='{mpi}' UCX_PREFIX='{ucx}'\n")
            with patch.dict(os.environ, {"TRIAL_MPI_TUNING": str(tuning),
                                         "UCX_TLS": "tcp", "PRIVATE_TEST_SECRET": "never-print-this"}):
                result = diagnostics.collect(root)
                out = diagnostics.write_report(root, result)
                self.assertEqual(os.environ["UCX_TLS"], "tcp")
            for arm in ("full", "reference"):
                data = result["arms"][arm]
                self.assertTrue(data["activated"])
                self.assertEqual(data["commands"]["ucx_devices"]["returncode"], 0)
                self.assertEqual(data["transports"], ["posix", "rc_mlx5"])
                self.assertIn("mlx5_2:1", data["devices"])
                self.assertEqual(data["runtime_settings"]["UCX_TLS"], "rc,sm,self")
            self.assertEqual(sentinel.read_text(), '{"preserve":true}\n')
            self.assertFalse((root / "MPI_WAS_LAUNCHED").exists())
            self.assertNotIn("never-print-this", (out / "report.json").read_text())
            self.assertNotIn("never-print-this", (out / "report.txt").read_text())
            self.assertEqual(json.loads((out / "report.json").read_text())["trial_root"], str(root))

    def test_missing_arm_is_reported_and_never_borrows_other_arm_prefixes(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"UCX_PREFIX": "/wrong/other-arm", "MPI_PREFIX": "/wrong/mpi"}):
                arm = diagnostics.collect_arm(Path(tmp), "reference")
            self.assertFalse(arm["activated"])
            self.assertIn("arm may be incomplete", arm["activation"])
            self.assertEqual(arm["prefixes"]["UCX_PREFIX"], str(Path(tmp) / "install/ucx-1.16.0-reference"))
            self.assertIsNone(arm["commands"]["ucx_devices"]["returncode"])

    def test_reports_active_and_down_ports_without_selecting_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            for device, state in (("mlx5_0", "4: ACTIVE"), ("mlx5_1", "1: DOWN")):
                port = base / device / "ports/1"
                port.mkdir(parents=True)
                (port / "state").write_text(state)
                (port / "link_layer").write_text("InfiniBand")
            ports = diagnostics.rdma_ports(base)
            self.assertEqual([p["device_port"] for p in ports], ["mlx5_0:1", "mlx5_1:1"])
            self.assertEqual(ports[1]["state"], "1: DOWN")

    def test_incomplete_activation_cannot_reuse_inherited_prefixes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "mpi-env-reference.sh").write_text("true\n")
            with patch.dict(os.environ, {"UCX_PREFIX": "/other/ucx", "MPI_PREFIX": "/other/mpi"}):
                env, note = diagnostics.activated_env(root, "reference")
            self.assertIsNone(env)
            self.assertIn("did not define", note)

    def test_rejects_wrong_root_before_creating_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run([sys.executable, str(SCRIPT), "--trial-root", tmp],
                                  capture_output=True, text=True)
            self.assertEqual(proc.returncode, 2)
            self.assertIn("No saved env.sh", proc.stderr)
            self.assertFalse((Path(tmp) / "results").exists())

    def test_missing_and_timed_out_tools_are_recorded(self):
        self.assertIsNone(diagnostics.run(["/nonexistent/trial-command"])["returncode"])
        result = diagnostics.run([sys.executable, "-c", "import time;time.sleep(2)"], timeout=0.05)
        self.assertIsNone(result["returncode"])
        self.assertIn("timed out", result["stderr"])


if __name__ == "__main__":
    unittest.main()
