"""Exercise startup diagnostics and timeouts without requiring an RDMA device."""

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from test_mpi_driver import REPO, executable

with patch.object(sys, "path", [str(REPO / "scripts"), *sys.path]):
    spec = importlib.util.spec_from_file_location("startup_probe", REPO / "scripts/probe_mpi_startup.py")
    startup = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(startup)


class StartupTests(unittest.TestCase):
    def test_component_comparison_keeps_saved_runtime_and_build_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            mpi = root / "private-mpi"
            (root / "runner/state").mkdir(parents=True)
            state = root / "runner/state/fftw-full.json"
            state.write_text("preserve existing evidence")
            (root / "env.sh").write_text("unset UCX_TLS\n")
            (root / "mpi-env.sh").write_text(
                f'source "$TRIAL_ROOT/env.sh"\nexport MPI_PREFIX="{mpi}" UCX_PREFIX="{root}/ucx"\n'
                'export OMPI_MCA_pml=ucx OMPI_MCA_btl="^uct"\n')
            tuning = root / "runtime.sh"
            tuning.write_text("export UCX_TLS=rc,sm,self\n")
            config = root / "runner/mpi-config.json"
            config.write_text(json.dumps({"tuning_file": str(tuning)}))
            before = config.read_bytes()
            executable(mpi / "bin/mpicc", """test "$UCX_TLS" = rc,sm,self
while test "$#" -gt 0; do
if test "$1" = -o; then shift; touch "$1"; break; fi
shift
done
""")
            executable(mpi / "bin/mpirun", """test "$UCX_TLS" = rc,sm,self
case " $* " in
*' --mca btl ^uct,openib'*) printf 'startup probe: rank 0 PASS\\nstartup probe: rank 1 PASS\\n';;
*' --mca btl self,vader '*) printf 'startup probe: rank 0 PASS\\nstartup probe: rank 1 PASS\\n';;
*) echo 'Failed to modify UD QP to INIT on mlx5_0: Operation not permitted'; exit 1;;
esac
""")
            with patch.dict(os.environ, {"SLURM_JOB_ID": "123", "SLURM_JOB_NODELIST": "node1"}), \
                 patch.object(startup.socket, "gethostname", return_value="node1"), \
                 patch.object(startup.subprocess, "check_output", return_value="node1\n"), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertFalse(startup.probe(root, "full", "saved", 2))
                self.assertTrue(startup.probe(root, "full", "no-openib", 2))
                self.assertTrue(startup.probe(root, "full", "no-openib-ofi", 2))
                self.assertTrue(startup.probe(root, "full", "local-btls", 2))
            reports = [json.loads(p.read_text()) for p in root.glob("results/diagnostics/*/report.json")]
            self.assertEqual(len(reports), 4)
            for report in reports:
                self.assertEqual(report["passed"], report["mode"] != "saved")
                self.assertEqual(report["runtime_settings"]["UCX_TLS"], "rc,sm,self")
                self.assertEqual(report["runtime_settings"]["OMPI_MCA_btl"], "^uct")
                self.assertIn(str(mpi / "bin/mpirun"), report["startup"]["command"])
                self.assertIn("--nooversubscribe", report["startup"]["command"])
            ofi = next(r for r in reports if r["mode"] == "no-openib-ofi")
            self.assertIn("^ofi", ofi["startup"]["command"])
            self.assertEqual(config.read_bytes(), before)
            self.assertEqual(state.read_text(), "preserve existing evidence")

    def test_hung_startup_is_terminated_and_retains_error_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "startup.log"
            started = time.monotonic()
            result = startup.run_logged([sys.executable, "-u", "-c",
                "import time; print('entering MPI_Init'); time.sleep(60)"], os.environ.copy(), log, 0.2)
            self.assertTrue(result["timed_out"])
            self.assertNotEqual(result["returncode"], 0)
            self.assertIn("entering MPI_Init", log.read_text())
            self.assertLess(time.monotonic() - started, 5)

    def test_probe_rejects_login_node_before_starting_processes(self):
        with patch.dict(os.environ, {"SLURM_JOB_ID": "123", "SLURM_JOB_NODELIST": "compute1"}), \
             patch.object(startup.socket, "gethostname", return_value="login1"), \
             patch.object(startup.subprocess, "check_output", return_value="compute1\n"), \
             patch.object(startup, "activated_env") as activate:
            with self.assertRaisesRegex(RuntimeError, "outside the allocation"):
                startup.probe(Path("/unused"), "full", "saved", 2)
            activate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
