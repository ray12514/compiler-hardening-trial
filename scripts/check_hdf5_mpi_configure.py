"""Configure the real pinned parallel HDF5 recipe without optional file-utils dependencies."""

import argparse
import hashlib
from pathlib import Path
import re
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, help="Pinned hdf5-2.1.0.tar.gz")
    parser.add_argument("--image", required=True,
                        help="Local Linux image with CMake >=3.26, GCC, make, Open MPI and Python 3")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    expected = re.search(r"^([0-9a-f]{64})  hdf5-2.1.0.tar.gz$",
                         (repo / "docs/standalone-hardening/00-gcc-bootstrap.md").read_text(), re.M)[1]
    archive = args.archive.expanduser().resolve(strict=True)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != expected:
        parser.error("HDF5 archive does not match the trial's pinned SHA-256")
    doc = (repo / "docs/standalone-hardening/05-parallel.md").read_text()
    recipe = re.findall(r"```bash\n(.*?)\n```", doc, re.S)[4]
    configure = recipe[recipe.index('    "$CMAKE" -S'):recipe.index('    "$CMAKE" --build')]
    script = """set -euo pipefail
export TRIAL_ROOT=/tmp/trial MPI_PREFIX=/usr CMAKE=cmake
export CFLAGS='-O2 -fPIC' SHARED_LDFLAGS='' EXE_LDFLAGS=''
mkdir -p "$TRIAL_ROOT/src"
tar -xf /input/hdf5-2.1.0.tar.gz -C "$TRIAL_ROOT/src"
for p in full reference; do
    build="$TRIAL_ROOT/build/hdf5-mpi-$p"
    prefix="$TRIAL_ROOT/install/hdf5-mpi/$p"
    mkdir -p "$TRIAL_ROOT/logs/hdf5-mpi/$p"
""" + configure + """
    python3 - "$build" <<'PY'
import pathlib, re, sys
build = pathlib.Path(sys.argv[1])
cache = (build/'CMakeCache.txt').read_text()
for key, value in {'HDF5_ENABLE_PARALLEL':'ON', 'HDF5_BUILD_TOOLS':'ON',
                   'HDF5_BUILD_PARALLEL_TOOLS':'OFF', 'BUILD_TESTING':'ON',
                   'HDF5_BUILD_HL_LIB':'ON'}.items():
    assert re.search(r'^'+key+r':BOOL='+value+r'$',cache,re.M), key
targets = (build/'CMakeFiles/TargetDirectories.txt').read_text()
assert '/testpar/' in targets, 'Parallel correctness test targets were not generated'
assert '/tools/src/h5dump/' in targets, 'Regular HDF5 tools were lost'
assert '/utils/tools/h5dwalk/' not in targets, 'Optional file-walk utility was retained'
assert not re.search(r'^MFU_LIBRARY:[^=]+=.+$',cache,re.M), 'MFU lookup was unexpectedly performed'
print('PASS: MPI HDF5, parallel tests and regular tools configured without MFU')
PY
done
"""
    with tempfile.TemporaryDirectory(prefix="hdf5-mpi-configure-") as tmp:
        harness = Path(tmp) / "check.sh"
        harness.write_text(script)
        result = subprocess.run([
            "docker", "run", "--rm", "--network", "none", "--entrypoint", "/bin/bash",
            "--mount", f"type=bind,source={archive},target=/input/hdf5-2.1.0.tar.gz,readonly",
            "--mount", f"type=bind,source={harness},target=/input/check.sh,readonly",
            args.image, "/input/check.sh",
        ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    lines = result.stdout.splitlines()
    if result.returncode:
        print("\n".join(lines[-65:]))
        raise SystemExit(result.returncode)
    print("\n".join(line for line in lines if line.startswith("PASS:")))


if __name__ == "__main__":
    main()
