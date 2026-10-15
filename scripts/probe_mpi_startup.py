"""Run a bounded two-rank MPI startup check on the current allocated compute node."""

import argparse
import datetime
import fcntl
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import tempfile

from collect_mpi_diagnostics import activated_env, selected_env


SOURCE = r"""#include <mpi.h>
#include <stdio.h>
int main(int argc, char **argv) {
    fprintf(stderr, "startup probe: entering MPI_Init\n"); fflush(stderr);
    MPI_Init(&argc, &argv);
    int rank, size, total, n; char host[MPI_MAX_PROCESSOR_NAME];
    MPI_Comm_rank(MPI_COMM_WORLD, &rank); MPI_Comm_size(MPI_COMM_WORLD, &size);
    MPI_Get_processor_name(host, &n);
    fprintf(stderr, "startup probe: rank %d/%d initialized on %s\n", rank, size, host);
    fflush(stderr);
    int one=1; MPI_Allreduce(&one, &total, 1, MPI_INT, MPI_SUM, MPI_COMM_WORLD);
    if(size != 2 || total != 2) { MPI_Abort(MPI_COMM_WORLD, 1); return 1; }
    MPI_Finalize();
    printf("startup probe: rank %d PASS\n", rank); return 0;
}
"""


def run_logged(command, env, log, timeout):
    with log.open("w") as output:
        proc = subprocess.Popen(command, env=env, stdout=output,
                                stderr=subprocess.STDOUT, start_new_session=True)
        timed_out = False
        try:
            proc.wait(timeout=timeout)
        except (subprocess.TimeoutExpired, KeyboardInterrupt) as error:
            timed_out = isinstance(error, subprocess.TimeoutExpired)
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                proc.wait()
            # A launcher can exit before a stuck local descendant. This is the
            # probe's own process group, never the interactive shell's group.
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            if not timed_out:
                raise
    return {"command": command, "returncode": proc.returncode, "timed_out": timed_out,
            "log": str(log)}


def probe(root, arm, mode, timeout):
    if not os.environ.get("SLURM_JOB_ID"):
        raise RuntimeError("Run inside the existing Slurm allocation on a compute node.")
    hosts = subprocess.check_output(["scontrol", "show", "hostnames", os.environ["SLURM_JOB_NODELIST"]],
                                    text=True, timeout=10).split()
    local = socket.gethostname().split(".")[0]
    host = next((name for name in hosts if name.split(".")[0] == local), None)
    if host is None:
        raise RuntimeError("Enter an allocated compute-node shell first; the current host is outside the allocation.")
    env, note = activated_env(root, arm)
    if env is None:
        raise RuntimeError(note)
    mpi = Path(env["MPI_PREFIX"])
    if not all((mpi / "bin" / name).is_file() for name in ("mpicc", "mpirun")):
        raise RuntimeError(f"Missing private MPI compiler/launcher in {mpi}; collect inventory first.")
    parent = root / "results/diagnostics"
    parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path(tempfile.mkdtemp(prefix=f"mpi-startup-{stamp}-{arm}-{mode}-", dir=parent))
    print(f"Probe evidence: {out}", flush=True)
    source, binary = out / "startup.c", out / "startup"
    source.write_text(SOURCE)
    result = {"arm": arm, "mode": mode, "host": host, "activation": note,
              "runtime_settings": selected_env(env), "mpi_prefix": str(mpi),
              "qualification": "Diagnostic only; one node does not verify inter-node RDMA."}
    result["compile"] = run_logged([str(mpi / "bin/mpicc"), "-O0", str(source), "-o", str(binary)],
                                   env, out / "compile.log", timeout)
    if result["compile"]["returncode"] == 0 and not result["compile"]["timed_out"]:
        command = [str(mpi / "bin/mpirun"), "-np", "2", "--host", host,
                   "--map-by", "slot", "--bind-to", "core", "--nooversubscribe",
                   "--mca", "pml", "ucx", "--mca", "pml_base_verbose", "20",
                   "--mca", "orte_base_help_aggregate", "0"]
        if mode == "local-btls":
            command += ["--mca", "btl", "self,vader"]
        elif mode != "saved":
            command += ["--mca", "btl", "^uct,openib" + (",ofi" if mode == "no-openib-ofi" else "")]
        if mode == "no-openib-ofi":
            command += ["--mca", "mtl", "^ofi"]
        command.append(str(binary))
        result["startup"] = run_logged(command, env, out / "startup.log", timeout)
    stage = result.get("startup", result["compile"])
    output = Path(stage["log"]).read_text(errors="replace")
    passed = ("startup" in result and stage["returncode"] == 0 and not stage["timed_out"]
              and all(f"startup probe: rank {rank} PASS" in output for rank in (0, 1)))
    result["passed"] = passed
    (out / "report.json").write_text(json.dumps(result, indent=2) + "\n")
    print("PASS" if passed else "TIMEOUT" if stage["timed_out"] else "FAIL", flush=True)
    print(output)
    print(f"Share {out / 'report.json'} and {stage['log']}")
    return passed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trial-root", type=Path,
                        default=Path(os.environ.get("TRIAL_ROOT", str(Path.home() / "COMPILER_HARDENING"))))
    parser.add_argument("--arm", choices=("full", "reference"), default="full")
    parser.add_argument("--mode", choices=("saved", "no-openib", "no-openib-ofi", "local-btls"), default="saved")
    parser.add_argument("--timeout", type=int, default=45, help="Seconds per compile/startup step (default 45)")
    args = parser.parse_args()
    if not 1 <= args.timeout <= 300:
        parser.error("Choose a timeout between 1 and 300 seconds.")
    root = args.trial_root.expanduser().resolve()
    if not (root / "env.sh").is_file():
        parser.error(f"No saved env.sh at {root}")
    try:
        with (root / "runner/lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError("A trial command is active. Stop that attempt before running this probe.") from None
            passed = probe(root, args.arm, args.mode, args.timeout)
    except (RuntimeError, OSError, KeyError, subprocess.SubprocessError) as error:
        parser.exit(1, f"ERROR: {error}\n")
    parser.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
