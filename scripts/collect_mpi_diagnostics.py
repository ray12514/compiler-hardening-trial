"""Collect local trial MPI/UCX evidence without running MPI or changing builds."""

import argparse
import datetime
import json
import os
from pathlib import Path
import platform
import re
import resource
import socket
import subprocess
import tempfile


ENV_KEYS = (
    "UCX_TLS", "UCX_NET_DEVICES", "UCX_IB_GID_INDEX", "UCX_IB_SL",
    "UCX_IB_TRAFFIC_CLASS", "UCX_LOG_LEVEL", "OMPI_MCA_pml", "OMPI_MCA_btl",
    "OMPI_MCA_plm", "OMPI_MCA_ras", "TRIAL_MPI_TUNING",
)


def run(command, env=None, timeout=20):
    try:
        proc = subprocess.run(command, env=env, capture_output=True, timeout=timeout)
        return {"command": command, "returncode": proc.returncode,
                "stdout": proc.stdout.decode(errors="replace"),
                "stderr": proc.stderr.decode(errors="replace")}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"command": command, "returncode": None, "stdout": "", "stderr": str(error)}


def selected_env(env):
    return {key: env[key] for key in ENV_KEYS if key in env}


def activated_env(root, arm):
    activation = root / ("mpi-env.sh" if arm == "full" else "mpi-env-reference.sh")
    if not activation.is_file():
        return None, f"Not present: {activation} (arm may be incomplete)"
    # Match the trial's saved activation in a non-login child shell. Capture the
    # environment for subprocesses, but never write a complete environment dump.
    code = """export TRIAL_ROOT="$1"
unset MPI_PREFIX UCX_PREFIX
source "$2" >/dev/null || exit $?
if test -n "${TRIAL_MPI_TUNING:-}"; then
    source "$TRIAL_MPI_TUNING" >/dev/null || exit $?
fi
env -0
"""
    child_env = os.environ.copy()
    for key in ("BASH_ENV", "ENV"):
        child_env.pop(key, None)
    result = run(["bash", "--noprofile", "--norc", "-c", code,
                  "trial-diagnostics", str(root), str(activation)], env=child_env)
    if result["returncode"] != 0:
        return None, result["stderr"] or "Saved activation failed"
    env = dict(item.split("=", 1) for item in result["stdout"].split("\0") if "=" in item)
    if any(not env.get(key) or not Path(env[key]).is_absolute()
           for key in ("MPI_PREFIX", "UCX_PREFIX")):
        return None, "Saved activation did not define absolute MPI_PREFIX and UCX_PREFIX"
    return env, "Saved activation and any selected tuning file applied in a child shell"


def text_file(path, limit=40000):
    try:
        with path.open("rb") as stream:
            stream.seek(max(0, path.stat().st_size - limit))
            return stream.read(limit).decode(errors="replace")
    except OSError as error:
        return f"Unavailable: {error}"


def rdma_ports(base=Path("/sys/class/infiniband")):
    ports = []
    for path in sorted(base.glob("*/ports/*")):
        ports.append({"device_port": f"{path.parents[1].name}:{path.name}",
                      **{name: text_file(path / name).strip()
                         for name in ("state", "phys_state", "link_layer", "rate")}})
    return ports


def collect_arm(root, arm):
    print(f"Collecting {arm} MPI/UCX inventory...", flush=True)
    suffix = "fixed" if arm == "full" else "reference"
    env, note = activated_env(root, arm)
    fallback = {"UCX_PREFIX": str(root / "install" / f"ucx-1.16.0-{suffix}"),
                "MPI_PREFIX": str(root / "install" / f"openmpi-4.1.8-ucx-{suffix}")}
    # Without activation, use the documented paths and label the observations
    # as unactivated; don't invent an MPI environment for an incomplete build.
    active = env if env is not None else os.environ.copy()
    prefixes = {key: active.get(key, value) if env is not None else value
                for key, value in fallback.items()}
    commands = {}
    for label, prefix, binary, arguments in (
        ("ucx_version", "UCX_PREFIX", "ucx_info", ["-v"]),
        ("ucx_devices", "UCX_PREFIX", "ucx_info", ["-d"]),
        ("mpi_version", "MPI_PREFIX", "ompi_info", ["--version"]),
        ("mpi_pml", "MPI_PREFIX", "ompi_info", ["--param", "pml", "ucx"]),
    ):
        executable = Path(prefixes[prefix]) / "bin" / binary
        commands[label] = run([str(executable), *arguments], env=active)
    component = Path(prefixes["MPI_PREFIX"]) / "lib/openmpi/mca_pml_ucx.so"
    commands["pml_libraries"] = run(["ldd", str(component)], env=active)
    devices = commands["ucx_devices"]["stdout"]
    logs = {}
    for package in ("ucx", "openmpi"):
        for filename in ("flags.txt", "configure.log", "build.log", "check.log"):
            path = root / "logs" / f"{package}-{suffix}" / filename
            if path.is_file():
                logs[str(path.relative_to(root))] = text_file(path)
    return {"activation": note, "activated": env is not None, "prefixes": prefixes,
            "runtime_settings": selected_env(active), "commands": commands,
            "transports": sorted(set(re.findall(r"^\s*#\s*Transport:\s*(\S+)", devices, re.M))),
            "devices": sorted(set(re.findall(r"^\s*#\s*Device:\s*(\S+)", devices, re.M))),
            "build_log_tails": logs}


def collect(root):
    limit = resource.getrlimit(resource.RLIMIT_MEMLOCK)
    result = {
        "trial_root": str(root), "host": socket.gethostname(), "platform": platform.platform(),
        "time_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "allocation": {key: os.environ[key] for key in (
            "SLURM_JOB_ID", "SLURM_JOB_NODELIST", "SLURM_JOB_NUM_NODES", "SLURM_STEP_ID")
            if key in os.environ},
        "memlock_bytes": {name: "unlimited" if value == resource.RLIM_INFINITY else value
                          for name, value in zip(("soft", "hard"), limit)},
        "inherited_runtime_settings": selected_env(os.environ),
        "runner_procedure": text_file(root / "runner/procedure.txt").strip(),
        "ports": rdma_ports(),
        "arms": {arm: collect_arm(root, arm) for arm in ("full", "reference")},
        "site_commands": {name: run([name]) for name in ("ibstat", "ibv_devinfo")},
    }
    # Include only recent MPI-related driver logs; do not copy arbitrary logs or
    # scheduler credentials into the report.
    logs = [p for p in (root / "logs/runner").glob("*.log")
            if any(word in p.name for word in ("mpi", "placement", "reframe"))]
    result["recent_mpi_log_tails"] = {
        str(p.relative_to(root)): text_file(p)
        for p in sorted(logs, key=lambda p: p.stat().st_mtime, reverse=True)[:3]}
    return result


def write_report(root, result):
    destination = root / "results/diagnostics"
    destination.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    host = re.sub(r"[^A-Za-z0-9_.-]", "_", result["host"])
    out = Path(tempfile.mkdtemp(prefix=f"mpi-{stamp}-{host}-", dir=destination))
    (out / "report.json").write_text(json.dumps(result, indent=2) + "\n")
    lines = [f"MPI/UCX diagnostic report: {result['host']}", f"Trial root: {root}",
             f"Allocation: {json.dumps(result['allocation'])}",
             f"Memlock bytes: {json.dumps(result['memlock_bytes'])}",
             f"Inherited runtime settings: {json.dumps(result['inherited_runtime_settings'])}",
             "Inventory only: no MPI launch or RDMA performance qualification was performed."]
    for arm, data in result["arms"].items():
        lines += [f"\n[{arm}] {data['activation']}", json.dumps(data["prefixes"]),
                  f"Runtime settings: {json.dumps(data['runtime_settings'])}",
                  f"Transports: {', '.join(data['transports']) or 'not reported'}",
                  f"Devices: {', '.join(data['devices']) or 'not reported'}"]
        for name, command in data["commands"].items():
            output = command["stdout"] if name != "ucx_devices" else "Full device inventory is in report.json."
            lines += [f"\n{name}: exit={command['returncode']}", output, command["stderr"]]
        for path, tail in data["build_log_tails"].items():
            lines += [f"\nBuild log tail: {path}", "\n".join(tail.splitlines()[-25:])]
    lines += ["\nRDMA ports:", json.dumps(result["ports"], indent=2)]
    for name, command in result["site_commands"].items():
        lines += [f"\n{name}: exit={command['returncode']}", command["stdout"], command["stderr"]]
    for path, tail in result["recent_mpi_log_tails"].items():
        lines += [f"\nRecent MPI log tail: {path}", "\n".join(tail.splitlines()[-35:])]
    (out / "report.txt").write_text("\n".join(lines) + "\n")
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trial-root", type=Path,
                        default=Path(os.environ.get("TRIAL_ROOT", str(Path.home() / "COMPILER_HARDENING"))))
    args = parser.parse_args()
    root = args.trial_root.expanduser().resolve()
    if not (root / "env.sh").is_file():
        parser.error(f"No saved env.sh at {root}; select the existing trial with --trial-root")
    result = collect(root)
    out = write_report(root, result)
    for arm, data in result["arms"].items():
        print(f"{arm}: transports={','.join(data['transports']) or 'not reported'}; "
              f"devices={','.join(data['devices']) or 'not reported'}")
    print(f"Report saved: {out}\nShare the contents of: {out / 'report.txt'}")
    print("No MPI jobs, downloads, rebuilds, state changes or tuning changes were requested.")


if __name__ == "__main__":
    main()
