"""Install the documented driver into an existing trial root."""

import argparse
import fcntl
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys


def install(root, repo):
    source = repo / "docs/standalone-hardening"
    code = re.search(r"```python\n(.*?)\n```", (source / "13-driver.md").read_text(), re.S)[1]
    compile(code, "trial.py", "exec")
    runner = root / "runner"
    runner.mkdir(exist_ok=True)
    with (runner / "lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("A trial command is active; install after it finishes.") from None
        recipes = runner / "recipes"
        recipes.mkdir(exist_ok=True)
        for path in source.glob("*.md"):
            shutil.copy2(path, recipes / path.name)
        for name, content in {
            "trial.py": code + "\n",
            "trial": "#!/bin/bash\nexec " + shlex.quote(sys.executable) + " "
                     + shlex.quote(str(runner / "trial.py")) + ' "$@"\n',
        }.items():
            temp = runner / (name + ".install-tmp")
            temp.write_text(content)
            if name == "trial":
                temp.chmod(0o755)
            temp.replace(runner / name)
        commit = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                                capture_output=True, text=True)
        (runner / "procedure.txt").write_text(commit.stdout.strip() if commit.returncode == 0 else "archive-snapshot")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trial-root", type=Path,
                        default=Path(os.environ.get("TRIAL_ROOT", str(Path.home() / "COMPILER_HARDENING"))))
    args = parser.parse_args()
    root = args.trial_root.expanduser().resolve()
    if sys.version_info < (3, 10) or not root.is_dir() or any(c.isspace() for c in str(root)):
        parser.error("Use Python 3.10+ and an existing trial directory with no whitespace.")
    try:
        install(root, Path(__file__).resolve().parents[1])
    except (RuntimeError, OSError) as error:
        parser.exit(1, f"ERROR: {error}\n")
    print(f"Driver installed: {root / 'runner/trial'}; existing build state and results retained.")


if __name__ == "__main__":
    main()
