"""Retire the old MPI dependency graph and select persistent RDMA build settings."""

import argparse
import datetime
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import shlex
import tempfile


PACKAGES = ("ucx", "openmpi", "fftw-mpi", "hdf5-mpi")


def require_local_path(path, root):
    if not path.is_relative_to(root) or not path.resolve().is_relative_to(root):
        raise RuntimeError(f"Recovery will not move symlinked or external state: {path}")
    if any(part.is_symlink() for part in (path, *path.parents) if part.is_relative_to(root)):
        raise RuntimeError(f"Recovery will not move symlinked or external state: {path}")


def load_driver(root):
    path = root / "runner/trial.py"
    if not path.is_file():
        raise RuntimeError("Install the updated driver first using scripts/install_driver.py.")
    spec = importlib.util.spec_from_file_location("recovery_driver", path)
    driver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(driver)
    if not hasattr(driver, "ucx_configure_args"):
        raise RuntimeError("Install the updated driver first using scripts/install_driver.py.")
    return driver


def recovery_plan(driver):
    driver.require_setup()
    root = driver.ROOT.resolve()
    require_local_path(root / "build/retired", root)
    require_local_path(driver.HERE / "mpi-config.json", root)
    for manifest in (root / "build/retired").glob("mpi-rdma-*/recovery.json"):
        if driver.read(manifest).get("status") not in ("retired", "rolled-back"):
            raise RuntimeError(f"Unfinished prior recovery; inspect {manifest} before moving more files.")
    for package in ("fftw", "hdf5", "blas", "lapack"):
        for arm in ("full", "reference"):
            if (driver.HERE / "state" / f"{package}-{arm}.json").exists():
                state = driver.verify_state(f"{package}-{arm}")
                if state.get("effective_profile") != driver.read(driver.HERE / "qualification.json"):
                    raise RuntimeError("Serial build qualification differs; retain this trial and inspect before recovery.")
    paths = set()
    for arm in ("full", "reference"):
        for package in PACKAGES:
            name = f"{package}-{arm}"
            build, prefix = driver.paths(package, arm)
            state, pending = (driver.HERE / folder / f"{name}.json" for folder in ("state", "pending"))
            managed = state.exists() or pending.exists()
            if (build.exists() or prefix.exists()) and not managed:
                raise RuntimeError(f"Unmanaged {name} directories; retain them and inspect before recovery.")
            if state.exists():
                driver.verify_state(name)
            paths.update((build, prefix, state, pending))
            suffix = "fixed" if arm == "full" else "reference"
            paths.add(root / "logs" / (f"{package}-{suffix}" if package in ("ucx", "openmpi") else f"{package}/{arm}"))
            if package.endswith("-mpi"):
                paths.add(root / "bench" / f"{package}-{suffix}")
        paths.add(root / ("mpi-env.sh" if arm == "full" else "mpi-env-reference.sh"))
        paths.add(root / "bench" / f"mpi-smoke-{arm}")
    existing = sorted((p for p in paths if p.exists() or p.is_symlink()), key=str)
    for path in existing:
        require_local_path(path, root)
        if path.stat().st_dev != (root / "build").stat().st_dev:
            raise RuntimeError(f"Recovery requires one filesystem for reversible renames: {path}")
    return existing


def check_prerequisites(driver, arguments):
    flags = []
    for arg in arguments:
        if "=" in arg:
            prefix = Path(arg.split("=", 1)[1])
            if not prefix.is_absolute() or not prefix.is_dir():
                raise RuntimeError(f"Missing absolute RDMA development prefix: {prefix}")
            flags.append(f"-I{prefix / 'include'}")
            flags.extend(f"-L{prefix / name}" for name in ("lib64", "lib") if (prefix / name).is_dir())
    with tempfile.TemporaryDirectory(prefix="rdma-prerequisites-", dir=driver.HERE) as tmp:
        probe = Path(tmp) / "probe"
        code = '"$CC" -x c - '+shlex.join(flags)+' -libverbs -lrdmacm -o '+shlex.quote(str(probe))+" <<'C'\n"
        code += "#include <infiniband/verbs.h>\n#include <rdma/rdma_cma.h>\n"
        code += "int main(void) { void *volatile v=(void *)&ibv_get_device_list; void *volatile r=(void *)&rdma_establish; return !v || !r; }\nC\n"
        code += shlex.quote(str(probe)) + "\n"
        driver.shell("rdma-prerequisites", code, profiles=False)


def retire(driver, paths, arguments, tuning=None):
    root = driver.ROOT
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    archive = root / "build/retired" / f"mpi-rdma-{stamp}"
    archive.mkdir(parents=True)
    manifest = archive / "recovery.json"
    record = {"status": "retiring", "trial_root": str(root), "ucx_configure_args": arguments,
              "procedure": driver.read(driver.HERE / "setup.json"),
              "previous_mpi_config": driver.read(driver.HERE / "mpi-config.json"),
              "moves": [{"from": str(p.relative_to(root)), "to": str(p.relative_to(root))} for p in paths]}
    driver.save(manifest, record)
    moved = []
    config = driver.HERE / "mpi-config.json"
    old_config = config.read_bytes() if config.exists() else None
    generated_tuning = driver.HERE / f"mpi-rdma-{stamp}.sh"
    try:
        for source in paths:
            destination = archive / source.relative_to(root)
            destination.parent.mkdir(parents=True, exist_ok=True)
            source.rename(destination)
            moved.append((source, destination))
        if tuning is None:
            generated_tuning.write_text("# CPU RDMA payload; shared memory and loopback remain available.\n"
                                        "export UCX_TLS=rc,sm,self\nunset UCX_NET_DEVICES\n")
            tuning = generated_tuning
        driver.save(config, {"ucx_configure_args": arguments, "tuning_file": str(tuning),
                             "recovery_manifest": str(manifest)})
        record["status"] = "retired"
        driver.save(manifest, record)
    except BaseException:
        # Roll back renames on preparation failure. Keep a journal if storage
        # failure also prevents rollback; never pretend that rollback succeeded.
        failures = []
        for source, destination in reversed(moved):
            try:
                destination.rename(source)
            except OSError as error:
                failures.append(str(error))
        try:
            if old_config is None:
                config.unlink(missing_ok=True)
            else:
                config.write_bytes(old_config)
            generated_tuning.unlink(missing_ok=True)
        except OSError as error:
            failures.append(str(error))
        record.update(status="rollback-incomplete" if failures else "rolled-back", rollback_errors=failures)
        driver.save(manifest, record)
        if failures:
            raise RuntimeError(f"Recovery preparation and rollback failed; inspect {manifest}") from None
        raise
    return archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trial-root", type=Path,
                        default=Path(os.environ.get("TRIAL_ROOT", str(Path.home() / "COMPILER_HARDENING"))))
    parser.add_argument("--apply", action="store_true", help="Run prerequisite check, then retire the MPI graph")
    parser.add_argument("--verbs-prefix", type=Path)
    parser.add_argument("--rdmacm-prefix", type=Path)
    parser.add_argument("--tuning-file", type=Path, help="Existing qualified site runtime file; otherwise use rc,sm,self and automatic device selection")
    args = parser.parse_args()
    root = args.trial_root.expanduser().resolve()
    arguments = ["--with-verbs" + ("=" + str(args.verbs_prefix.expanduser().resolve()) if args.verbs_prefix else ""),
                 "--with-rdmacm" + ("=" + str(args.rdmacm_prefix.expanduser().resolve()) if args.rdmacm_prefix else "")]
    try:
        if args.tuning_file and not args.tuning_file.expanduser().is_file():
            raise RuntimeError("The selected tuning file does not exist.")
        override = os.environ.get("TRIAL_UCX_CONFIGURE_ARGS")
        if override is not None and shlex.split(override) != arguments:
            raise RuntimeError("Unset the conflicting TRIAL_UCX_CONFIGURE_ARGS before selecting RDMA recovery.")
        driver = load_driver(root)
        with (driver.HERE / "lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError("Another trial command is active; wait for it to finish.") from None
            previous = driver.read(driver.HERE / "mpi-config.json", {})
            if previous.get("recovery_manifest"):
                if previous.get("ucx_configure_args") != arguments:
                    raise RuntimeError("A different MPI recovery is already recorded; inspect runner/mpi-config.json.")
                if driver.read(Path(previous["recovery_manifest"]), {}).get("status") != "retired" or not Path(previous.get("tuning_file", "")).is_file():
                    raise RuntimeError("The recorded MPI recovery is incomplete; inspect its manifest and tuning file.")
                print("RDMA recovery is already recorded. Resume trial build all --retry; existing progress is retained.")
                return
            paths = recovery_plan(driver)
            print("RDMA selection:", " ".join(arguments))
            print("Preserve serial FFTW/HDF5/BLAS/LAPACK, GCC, source downloads, qualification and results.")
            print("Retire old UCX/Open MPI and MPI payloads for both arms:")
            for path in paths:
                print(" ", path.relative_to(root))
            if not args.apply:
                print("Plan only. Stop running/queued trial jobs, then repeat with --apply in a build allocation.")
                return
            if not os.environ.get("SLURM_JOB_ID"):
                raise RuntimeError("Apply recovery inside the site's Slurm build allocation.")
            driver.verify_mpi_archives()
            check_prerequisites(driver, arguments)
            archive = retire(driver, paths, arguments,
                             args.tuning_file.expanduser().resolve() if args.tuning_file else None)
            print(f"Previous MPI files and records preserved at {archive}")
            print(f"Next: {root / 'runner/trial'} build all --retry")
    except (RuntimeError, OSError, ValueError) as error:
        parser.exit(1, f"ERROR: {error}\n")


if __name__ == "__main__":
    main()
