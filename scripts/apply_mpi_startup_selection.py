"""Save a passing startup probe's component selection, without its CPU sharing options."""

import argparse
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shlex
import tempfile

from collect_mpi_diagnostics import activated_env


COMPONENTS = {
    "saved": {},
    "no-openib": {"OMPI_MCA_btl": "^uct,openib"},
    "no-openib-ofi": {"OMPI_MCA_btl": "^uct,openib,ofi", "OMPI_MCA_mtl": "^ofi"},
    "local-btls": {"OMPI_MCA_btl": "self,vader"},
}


def atomic_write(path, text):
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as output:
        temporary = Path(output.name)
        output.write(text)
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def apply(root, report_path=None):
    if report_path is None:
        reports = list((root / "results/diagnostics").glob("mpi-startup-*/report.json"))
        if not reports:
            raise RuntimeError("No startup probe report found. Run the startup probe first.")
        report_path = max(reports, key=lambda path: path.stat().st_mtime_ns)
    report_path = report_path.expanduser().resolve()
    raw = report_path.read_bytes()
    report = json.loads(raw)
    if report.get("passed") is not True or report.get("arm") not in ("full", "reference"):
        raise RuntimeError("The selected/latest probe did not pass. Retain its logs; no runtime selection was changed.")
    mode = report.get("mode")
    if mode not in COMPONENTS:
        raise RuntimeError("Unknown startup component selection; no settings changed.")
    runner = root / "runner"
    config_path = runner / "mpi-config.json"
    config = json.loads(config_path.read_text()) if config_path.exists() else {}
    previous = config.get("tuning_file") or os.environ.get("TRIAL_MPI_TUNING")
    report_hash = hashlib.sha256(raw).hexdigest()
    selection = config.get("startup_selection", {})
    if selection.get("report_sha256") == report_hash:
        tuning = Path(previous or "")
        if not tuning.is_file() or hashlib.sha256(tuning.read_bytes()).hexdigest() != selection.get("tuning_sha256"):
            raise RuntimeError("The saved runtime selection changed; inspect it before applying again.")
        print(f"Selection already saved: {tuning}")
        return tuning
    env, note = activated_env(root, report["arm"])
    if env is None:
        raise RuntimeError(note)
    if str(Path(env["MPI_PREFIX"]).resolve()) != str(Path(report.get("mpi_prefix", "")).resolve()):
        raise RuntimeError("The passing probe used a different MPI prefix; run it again for this trial.")
    for name in ("UCX_TLS", "UCX_NET_DEVICES", "UCX_IB_GID_INDEX", "UCX_IB_SL", "UCX_IB_TRAFFIC_CLASS"):
        if env.get(name) != report.get("runtime_settings", {}).get(name):
            raise RuntimeError(f"{name} changed since the probe; repeat startup before saving its selection.")
    text = "# Component selection from a passing local startup probe; inter-node RDMA is still unverified.\n"
    if previous:
        previous_path = Path(previous).expanduser()
        if not previous_path.is_absolute() or not previous_path.is_file():
            raise RuntimeError("The existing runtime file is missing or not absolute; no settings changed.")
        text += "source " + shlex.quote(str(previous_path)) + "\n"
    for key, value in {"OMPI_MCA_pml": "ucx", **COMPONENTS[mode]}.items():
        text += "export " + key + "=" + shlex.quote(value) + "\n"
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    tuning = runner / f"mpi-startup-selection-{stamp}.sh"
    atomic_write(tuning, text)
    config.update(tuning_file=str(tuning), startup_selection={
        "report": str(report_path), "report_sha256": report_hash,
        "mode": mode, "tuning_sha256": hashlib.sha256(tuning.read_bytes()).hexdigest(),
        "scope": "local startup only; CPU oversubscription and binding options were not copied",
    })
    try:
        atomic_write(config_path, json.dumps(config, indent=2) + "\n")
    except BaseException:
        tuning.unlink(missing_ok=True)
        raise
    print(f"Saved {mode} component selection for both arms: {tuning}")
    print("Existing fabric settings retained. Probe oversubscription/binding options were not copied.")
    print("Next: trial status, then trial build all --retry in a sufficiently sized build allocation.")
    return tuning


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trial-root", type=Path,
                        default=Path(os.environ.get("TRIAL_ROOT", str(Path.home() / "COMPILER_HARDENING"))))
    parser.add_argument("--report", type=Path, help="Specific passing report; default is the latest startup report")
    args = parser.parse_args()
    root = args.trial_root.expanduser().resolve()
    if not (root / "env.sh").is_file() or not (root / "runner").is_dir():
        parser.error("Select an existing trial with env.sh and runner/.")
    try:
        with (root / "runner/lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError("A driver command is active; stop/wait for it before changing runtime settings.") from None
            apply(root, args.report)
    except (RuntimeError, OSError, ValueError, TypeError, AttributeError) as error:
        parser.exit(1, f"ERROR: {error}\n")


if __name__ == "__main__":
    main()
