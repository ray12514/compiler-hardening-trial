"""Exercise installed-driver MPI settings through its real generated shells."""

import contextlib
import importlib.util
import io
import os
from pathlib import Path
import re
import shutil
import tempfile
import types
import unittest
from unittest.mock import patch


REPO = Path(__file__).resolve().parents[1]


def driver_at(root):
    runner = root / "runner"
    runner.mkdir(parents=True, exist_ok=True)
    recipes = runner / "recipes"
    recipes.mkdir(exist_ok=True)
    for path in (REPO / "docs/standalone-hardening").glob("*.md"):
        shutil.copy2(path, recipes / path.name)
    code = re.search(r"```python\n(.*?)\n```", (recipes / "13-driver.md").read_text(), re.S)[1]
    (runner / "trial.py").write_text(code)
    spec = importlib.util.spec_from_file_location("fixture_driver", runner / "trial.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def executable(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/bash\nset -eu\n" + body)
    path.chmod(0o755)


class DriverSettingsTests(unittest.TestCase):
    def test_ucx_prefix_stays_in_shell_but_not_h5diff_process_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            driver = driver_at(root)
            (root / "env.sh").write_text("")
            (root / "profiles.sh").write_text('''activate_mpi_profile() {
    if test "$1" = reference; then source "$TRIAL_ROOT/mpi-env-reference.sh";
    else source "$TRIAL_ROOT/mpi-env.sh"; fi
}
''')
            tuning = root / "fabric.sh"
            tuning.write_text('export UCX_PREFIX="$TRIAL_ROOT/ucx"\nexport UCX_TLS=rc,sm,self\n')
            driver.save(driver.HERE / "mpi-config.json", {"tuning_file": str(tuning)})
            for name in ("mpi-env.sh", "mpi-env-reference.sh"):
                (root / name).write_text('export UCX_PREFIX="$TRIAL_ROOT/ucx"\n')
            executable(root / "ucx/bin/ph5diff", '''test "$UCX_TLS" = rc,sm,self
test -z "${UCX_WARN_UNUSED_ENV_VARS+x}"
if test -n "${UCX_PREFIX+x}"; then
    echo 'UCX WARN unused environment variable: UCX_PREFIX'
fi
echo '0 differences found'
''')
            activations = ('activate_mpi_profile full', 'activate_mpi_profile reference',
                           'source "$TRIAL_ROOT/mpi-env.sh"',
                           'source "$TRIAL_ROOT/mpi-env-reference.sh"')
            with patch.dict(os.environ, {}, clear=True), contextlib.redirect_stdout(io.StringIO()):
                for activation in activations:
                    with self.subTest(activation=activation):
                        output = driver.shell("h5diff-output", activation + '''
test "$UCX_PREFIX" = "$TRIAL_ROOT/ucx"
"$UCX_PREFIX/bin/ph5diff"
''', capture=True)
                        self.assertEqual(output.strip(), "0 differences found")

    def test_saved_rdma_build_selection_survives_a_new_shell(self):
        with tempfile.TemporaryDirectory() as tmp:
            driver = driver_at(Path(tmp))
            driver.save(driver.HERE / "mpi-config.json", {
                "ucx_configure_args": ["--with-verbs", "--with-rdmacm"],
                "tuning_file": str(Path(tmp) / "rdma-runtime.sh"),
            })
            with patch.dict(os.environ, {}, clear=True):
                self.assertEqual(driver.ucx_configure_args(), ["--with-verbs", "--with-rdmacm"])
                self.assertEqual(driver.environment()["TRIAL_MPI_TUNING"], str(Path(tmp) / "rdma-runtime.sh"))

    def test_both_smoke_arms_and_reframe_receive_tuning_after_activation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            driver = driver_at(root)
            (root / "bench").mkdir()
            (root / "env.sh").write_text("unset UCX_TLS UCX_NET_DEVICES OMPI_MCA_plm_slurm_args\n")
            (root / "profiles.sh").write_text("""profile_flags() { EXE_CFLAGS=-O2; EXE_LDFLAGS=-no-pie; }
activate_mpi_profile() {
    if test "$1" = reference; then source "$TRIAL_ROOT/mpi-env-reference.sh";
    else source "$TRIAL_ROOT/mpi-env.sh"; fi
}
""")
            tuning = root / "rdma-runtime.sh"
            tuning.write_text("export UCX_TLS=rc,sm,self\nunset UCX_NET_DEVICES\n"
                              "export OMPI_MCA_btl='^uct,openib,ofi' OMPI_MCA_mtl='^ofi'\n"
                              "export OMPI_MCA_plm_slurm_args='--kill-on-bad-exit=1'\n")
            for arm, name in (("full", "mpi-env.sh"), ("reference", "mpi-env-reference.sh")):
                mpi = root / arm
                (root / name).write_text(
                    f'source "$TRIAL_ROOT/env.sh"\nexport MPI_PREFIX="{mpi}"\n')
                executable(mpi / "bin/mpicc", """while test "$#" -gt 0; do
if test "$1" = -o; then shift; printf '#!/bin/bash\\nexit 0\\n' > "$1"; chmod +x "$1"; break; fi
shift
done
""")
                executable(mpi / "bin/mpirun", f"""test "${{UCX_TLS:-missing}}" = rc,sm,self
test -z "${{UCX_NET_DEVICES:-}}"
test "$OMPI_MCA_plm_slurm_args" = '--kill-on-bad-exit=1 --overlap'
case " $* " in *' -np 8 --host node1:4,node2:4 --nooversubscribe --map-by ppr:4:node '*) ;; *) exit 9;; esac
case " $* " in *' --mca btl ^uct,openib,ofi '*) ;; *) exit 9;; esac
printf '%s\\n' '{arm}' >> "$TRIAL_ROOT/seen-arms.txt"
""")
            reframe = root / "tools/reframe-venv/bin/reframe"
            executable(reframe, """if test "$1" = --version; then echo 4.10.4; exit 0; fi
test "${UCX_TLS:-missing}" = rc,sm,self
test "$OMPI_MCA_btl" = '^uct,openib,ofi'
test "$OMPI_MCA_plm_slurm_args" = '--kill-on-bad-exit=1 --overlap'
test -z "${UCX_LOG_LEVEL+x}"
echo reframe >> "$TRIAL_ROOT/seen-arms.txt"
""")
            driver.save(driver.HERE / "qualification.json", {})
            args = types.SimpleNamespace(package="fftw", mpi=True, nodes=2, pairs=10,
                                         ranks_per_node=4, slurm_overlap=True)
            with patch.dict(os.environ, {"SLURM_JOB_ID": "123", "SLURM_JOB_NODELIST": "node[1-2]",
                                         "TRIAL_MPI_TUNING": str(tuning), "UCX_TLS": "tcp"}), \
                 patch.object(driver, "require_setup", return_value={}), \
                 patch.object(driver, "check_reframe", return_value=reframe), \
                 patch.object(driver, "verify_state", return_value={"effective_profile": {}}), \
                 patch.object(driver.subprocess, "check_output", return_value="node1\nnode2\n"), \
                 patch.object(driver.os, "sched_getaffinity", return_value={0}, create=True), \
                 contextlib.redirect_stdout(io.StringIO()):
                driver.test(args)
            self.assertEqual((root / "seen-arms.txt").read_text().splitlines(), ["full", "reference", "reframe"])


if __name__ == "__main__":
    unittest.main()
