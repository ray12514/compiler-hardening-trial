"""Exercise the actual UCX configure recipe with Go available, without network."""

import argparse
import hashlib
from pathlib import Path
import re
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, help="Pinned ucx-1.16.0.tar.gz")
    parser.add_argument("--image", default="golang:1.25.13-bookworm")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    doc = (repo / "docs/standalone-hardening/00b-openmpi-ucx.md").read_text()
    expected = re.search(r"^([0-9a-f]{64})  ucx-1.16.0.tar.gz$", doc, re.M)[1]
    archive = args.archive.resolve(strict=True)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != expected:
        parser.error("UCX archive does not match the recipe's pinned SHA-256")
    blocks = re.findall(r"```bash\n(.*?)\n```", doc, re.S)
    recipe = next(block for block in blocks if "contrib/configure-release" in block)
    configure = recipe[recipe.index("  CC=") : recipe.index("\n  make -j")]
    # Exercise the optional-binding selection, with the real release and real Go.
    # Hardening qualification and target fabric acceptance are separate checks.
    script = """set -euo pipefail
export TRIAL_ROOT=/tmp/trial CC=gcc CXX=g++
export UCX_PREFIX="$TRIAL_ROOT/install/ucx"
export AUTOTOOLS_CFLAGS= AUTOTOOLS_CXXFLAGS= AUTOTOOLS_LDFLAGS=
tag=ucx-fixed
UCX_TRANSPORT_ARGS=(--without-verbs --without-rdmacm)
mkdir -p "$TRIAL_ROOT/src" "$TRIAL_ROOT/logs/$tag" "$TRIAL_ROOT/build"
tar -xf /input/ucx-1.16.0.tar.gz -C "$TRIAL_ROOT/src"
cd "$TRIAL_ROOT/build"
""" + configure + """
make -C bindings/go all > /tmp/go-build.log 2>&1 || {
    cat /tmp/go-build.log
    exit 1
}
make -n -C bindings/go all > /tmp/go-plan.log 2>&1
if grep -Eq '(^|[[:space:]])go (build|env|test)' /tmp/go-plan.log; then
    cat /tmp/go-plan.log
    exit 1
fi
echo 'PASS: actual UCX recipe skips optional Go bindings with Go installed'
"""
    with tempfile.TemporaryDirectory(prefix="ucx-go-check-") as tmp:
        harness = Path(tmp) / "check.sh"
        harness.write_text(script)
        result = subprocess.run(
            [
                "docker", "run", "--rm", "--network", "none",
                "--mount", f"type=bind,source={archive},target=/input/ucx-1.16.0.tar.gz,readonly",
                "--mount", f"type=bind,source={harness},target=/input/check.sh,readonly",
                args.image, "bash", "/input/check.sh",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        print("\n".join(result.stdout.splitlines()[-35:]))
        if result.returncode:
            raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
