# Standalone compiler hardening trial

Use private GCC 12.5.0 to compare the supplied hardening controls with a matched reference for FFTW, HDF5 and LAPACK. The normal workflow is now **prepare downloads on a login node → setup → build → test**. The driver handles profiles, flag qualification, prerequisites, callers and measurement files. The numbered runbooks contain the recipes it runs; you do not need to jump through their sections.

If you are continuing a trial from the earlier Planning checkout, use the
[existing trial handoff](#existing-trial-from-the-earlier-planning-checkout)
first. For a new trial with GCC bootstrap and `profiles.sh` complete, start at
step 1, then run setup. Setup does not rebuild GCC.

## Existing trial from the earlier Planning checkout

The public repository is now `compiler-hardening-trial`. Your existing checkout
may still be named `stack-planning-hardening` or something else. Its name does
not control the trial's state: the installer uses `RUNBOOK_REPO` for source and
`TRIAL_ROOT` for the existing environment, runner, downloads, installations and
results.

Wait until builds/tests and queued campaigns using this trial tree have stopped.
Use the same trial root you have already been building in. The commands below
use the established `~/COMPILER_HARDENING` layout; if your root differs, set
`TRIAL_ROOT` to that existing path. Run in Bash on the login/staging node, with
the same site modules and Python 3.10+ used for the trial.

```bash
set +e
set +u
set +o pipefail
export TRIAL_ROOT="$HOME/COMPILER_HARDENING"
test -f "$TRIAL_ROOT/env.sh"
```

**Stop if `env.sh` is missing.** Locate the existing trial root before continuing.
Clone the public source alongside your old checkout:

```bash
git clone --branch main --single-branch \
  https://github.com/ray12514/compiler-hardening-trial.git \
  "$TRIAL_ROOT/compiler-hardening-trial"
```

Stop if cloning fails. If that new directory already exists, use step 1 to
inspect/update it instead of cloning over it. Keep the old checkout and its
local edits. The repositories have separate histories; do not pull the new
repository into the old one or merge their histories. No rename, remote change
or reset of the old checkout is needed.

Next, follow **step 1 below, including its Python installer**. This selects the
new checkout and refreshes `runner/trial.py`, its launcher and recipe snapshot
inside the existing trial root. It leaves build records, installed packages,
saved environment files and results in place. Pulling Git alone does not update
the installed driver.

Then use [the login-node preparation section](#before-the-compute-allocation-prepare-mpi-sources-and-reframe-on-the-login-node)
to run `prepare-mpi` and `prepare-tests`. Back in a compute allocation, run:

```bash
"$TRIAL_ROOT/runner/trial" status
"$TRIAL_ROOT/runner/trial" prepare-mpi --check
"$TRIAL_ROOT/runner/trial" prepare-tests --check
```

For the earlier **`mpi-sources` failure**, resume with `trial build all --retry`
using the full launcher path shown below. If no build failed, use `trial build
all` to continue the original all-package build. The driver verifies and skips
unchanged completed artifacts. If only testing remains, go directly to step 4
for the package you finished. Keep the same trial root and build settings.

The MPI-source/ReFrame preparation update does not require repeating setup or
flag qualification. If the driver reports stale generated measurement files or
changed environment/qualification inputs, follow its specific setup instruction
on the build/compute node. A changed profile recipe after completed builds needs
a separate trial root; retain the current root and its results.

## 1. Pull updates and install the driver

Your working directory is `~/COMPILER_HARDENING`; the Git checkout is inside it. Builds, installations and results stay beside the checkout:

```text
~/COMPILER_HARDENING/
  compiler-hardening-trial/       Git checkout (use its actual name below)
  env.sh, site-env.sh             saved toolchain and site configuration
  profiles.sh, mpi-env*.sh        generated profiles and MPI activation
  runner/                        command, recipe snapshot, logs/state references
  downloads/, src/, build/, install/, toolchains/, tools/
  bench/, reframe/, logs/, results/
```

Use Bash: type `bash` once if your current shell is something else. If you are already in Bash, do not open another nested Bash. The first three commands below turn off error options left by the older instructions, so a failed inspection command does not close your shell. Load your site’s required master modules in their normal order before continuing.

```bash
set +e
set +u
set +o pipefail
export TRIAL_ROOT="$HOME/COMPILER_HARDENING"
export RUNBOOK_REPO="$TRIAL_ROOT/compiler-hardening-trial"
cd "$RUNBOOK_REPO"
git status --short
git switch main
git pull --ff-only
git rev-parse HEAD
```

Record the printed commit with the experiment results. **Stop here if Git reports an error.** Retain local edits and resolve the checkout issue before installing. `git pull` belongs in the Git checkout, not in the working root or `build/`. Do not update while tests are queued or running.

Install/update the command and its recipe snapshot using Python 3.10 or newer:

```bash
python3 - <<'PY'
import fcntl, os, pathlib, re, shlex, shutil, subprocess, sys
if sys.version_info < (3,10): raise SystemExit('Use Python 3.10 or newer for this installer and ReFrame.')
root = pathlib.Path(os.environ['TRIAL_ROOT']).expanduser().resolve()
repo = pathlib.Path(os.environ['RUNBOOK_REPO']).expanduser().resolve()
if any(c.isspace() for c in str(root)): raise SystemExit('TRIAL_ROOT must have no whitespace.')
source = repo/'docs/standalone-hardening'
code = re.findall(r'```python\n(.*?)\n```', (source/'13-driver.md').read_text(), re.S)[0]
compile(code, 'trial.py', 'exec')
runner = root/'runner'; runner.mkdir(parents=True, exist_ok=True)
with (runner/'lock').open('w') as lock:
    try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError: raise SystemExit('A trial command is active; install after it finishes.')
    recipes = runner/'recipes'; recipes.mkdir(exist_ok=True)
    for path in source.glob('*.md'): shutil.copy2(path, recipes/path.name)
    (runner/'trial.py').write_text(code+'\n')
    launcher = runner/'trial'
    launcher.write_text('#!/bin/bash\nexec '+shlex.quote(sys.executable)+' '+shlex.quote(str(runner/'trial.py'))+' "$@"\n')
    launcher.chmod(0o755)
    commit = subprocess.run(['git','-C',str(repo),'rev-parse','HEAD'], capture_output=True,text=True)
    (runner/'procedure.txt').write_text(commit.stdout.strip() if commit.returncode == 0 else 'archive-snapshot')
print('Installed. On the login node: prepare-mpi before MPI builds, prepare-tests before testing. New trials then run setup on a build/compute node.')
PY
```

A Git pull updates the documentation; running this installer updates the command
snapshot. New trials continue to setup in step 2. Existing trials use the handoff
above and rerun setup only when the updated driver requires it. For an archive
checkout, extract the new source to a separate directory and point `RUNBOOK_REPO`
there before installing; keep the existing trial root.

For a new machine without `env.sh`, first complete [the site environment](00-build-environment.md), then [00 — GCC bootstrap](00-gcc-bootstrap.md), through the saved environment file and source downloads. Those are the only manual prerequisites before step 2. A working `/usr/bin/gcc` and `/usr/bin/g++` can seed the private GCC build. [Offline GCC prerequisites](00-gcc-bootstrap.md#stage-gcc-prerequisites-for-a-machine-without-download-access) and [FFTW mirror retries](00-gcc-bootstrap.md#retry-fftw-after-a-certificate-error) are covered there.

## Before the compute allocation: prepare MPI sources and ReFrame on the login node

After bootstrap has created `env.sh` and step 1 has installed the driver, run this on a login node with approved package-index access:

```bash
export TRIAL_ROOT="$HOME/COMPILER_HARDENING"
"$TRIAL_ROOT/runner/trial" prepare-mpi
"$TRIAL_ROOT/runner/trial" prepare-tests
```

`prepare-mpi` downloads the pinned Open MPI 4.1.8 and UCX 1.16.0 release archives into `downloads/`, verifies SHA-256, and reuses valid cached files. It is needed for `build all` and `build PACKAGE --mpi`; serial-only builds do not need it. Compute builds only verify/extract the local archives and never download MPI sources. To check staging on a compute node, run `"$TRIAL_ROOT/runner/trial" prepare-mpi --check`.

`prepare-tests` prepares ReFrame 4.10.4 and its Python dependencies under `tools/reframe-venv` on the shared filesystem. It records the installed package versions and checks the environment. It can be done before payload builds or afterward, before the first test. It does not compile GCC or any trial packages. Compute-node `test` commands never install from pip/PyPI; a missing or unusable ReFrame produces a preparation instruction immediately.

Use the same Python 3.10+ installation/module on login and compute nodes, available at the same absolute path, with compatible Linux architecture and runtime libraries. Keep `TRIAL_ROOT` at the same shared path. A virtual environment refers to its base Python installation; copying a Mac environment or moving a venv is not a supported staging method. [Python venv documentation](https://docs.python.org/3/library/venv.html#how-venvs-work).

**If your build stopped at `mpi-sources`:** the old driver attempted a download from the compute node. Once the command has stopped, pull this update and rerun step 1's installer. Run `prepare-mpi` on the login node, then resume on the compute node with:

```bash
"$TRIAL_ROOT/runner/trial" build all --retry
```

Completed FFTW/HDF5/LAPACK/BLAS builds are verified and skipped. This preparation fix needs no repeat of `setup`, flag qualification or completed package builds. Prepare ReFrame with `prepare-tests` on the login node as well if you have not done that yet. If a build is still running, wait before updating the runner.

If MPI archives must be transferred from another connected host, download the exact release archives listed in [00b, source staging](00b-openmpi-ucx.md#1-stage-exact-mpi-sources) and transfer both files through the site's transfer route. Then run:

```bash
"$TRIAL_ROOT/runner/trial" prepare-mpi --from-dir /absolute/path/to/transferred-archives
```

That command imports and verifies `openmpi-4.1.8.tar.bz2` and `ucx-1.16.0.tar.gz` without downloading. Failed downloads never become accepted cache files; an invalid older archive is preserved when replaced. Certificate verification stays enabled. A certificate failure on the login node requires the site's trusted CA configuration or the transfer route above.

If the login node cannot reach the package index either, download wheels on a compatible connected Linux staging machine using the same Python version:

```bash
python3 -m pip download --only-binary=:all: 'reframe-hpc==4.10.4' -d reframe-wheels
```

Transfer the complete `reframe-wheels` directory through the site's transfer route. Then install into the trial's shared environment using only local wheels:

```bash
"$TRIAL_ROOT/runner/trial" prepare-tests --wheelhouse /absolute/path/to/reframe-wheels
```

If a dependency has no compatible wheel, prepare one on the compatible staging host with `python3 -m pip wheel 'reframe-hpc==4.10.4' -w reframe-wheels` before transfer. The offline installation disables the package index; retain the wheel directory and the generated `tools/reframe-venv/installed.txt`. [pip local installation documentation](https://pip.pypa.io/en/stable/user_guide/#installing-from-local-packages).

## 2. Set up and qualify the flags

```bash
"$TRIAL_ROOT/runner/trial" setup
```

Run this on an approved build/compute node representative of the test CPUs. It loads the saved GCC environment in child shells, creates `profiles.sh`, tests C/C++/Fortran and shared/executable links, and prepares the timing/ReFrame helpers. **Yes, flag qualification happens before Open MPI and package builds.** No package performance tests run at this stage.

The complete listed profile uses strong stack protection, C/C++ FORTIFY 2, RELRO/NOW, and PIE for executables; shared libraries retain PIC. Fortran FORTIFY is not applicable. The optional extended set is a separate experiment configured before building; the driver uses the set saved in `env.sh`.

On success, setup prints `Qualified complete-HASH`, or `Qualified compatible-HASH` if a requested control was explicitly rejected. A rejected control triggers a recorded adjustment and a fresh probe automatically. See `runner/qualification.json` for exact flags and `runner/policy.json` for the reason. A reduced result measures that effective set, not the complete supplied list. Other compiler, runtime or artifact failures stop and show the log; accepting an option alone does not prove protection is present.

You do not need to source `env.sh` or paste the sections of 01. Setup also repairs the old generated `env.sh` line that enabled interactive `set -e` and saves a backup in `runner/`.

## 3. Build the packages

After login-node `prepare-mpi` completes, build everything in a site-approved Slurm build allocation (MPI package correctness tests launch MPI processes):

```bash
"$TRIAL_ROOT/runner/trial" build all
```

Or build one independent package:

```bash
"$TRIAL_ROOT/runner/trial" build fftw
```

| Command after `trial` | Builds and upstream checks |
|---|---|
| `build fftw` | Serial/threaded FFTW and both matching callers |
| `build hdf5` | Serial HDF5 and both matching callers |
| `build lapack` | BLAS, LAPACK and both matching callers |
| `build fftw --mpi` | Serial FFTW, private UCX/Open MPI, MPI FFTW and callers |
| `build hdf5 --mpi` | Serial HDF5, private UCX/Open MPI, MPI HDF5 and callers |
| `build all` | All of the above, reusing completed prerequisites |

Each selected package starts with the complete applicable profile, then its reference. Control-removal experiments come after the first measurements. UCX/Open MPI are private builds; the site's Slurm and fabric installation are used. The default UCX configuration uses TCP/shared memory. If testing IB/RoCE, set `TRIAL_UCX_CONFIGURE_ARGS="--with-verbs --with-rdmacm"` before the first MPI build, with the site development dependencies available; see [driver details](13-driver.md).

Completed driver builds are checked and skipped on a repeated command. On failure, read the printed log, correct the reported issue, and rerun the same command with `--retry`, for example:

```bash
"$TRIAL_ROOT/runner/trial" build fftw --retry
```

This preserves the failed attempt and starts its build again. It does not remove more flags because of an arbitrary package/test failure. Existing manual installations are retained; the driver will explain if an audit or a separate trial root is needed. Changing build flags/dependencies after a successful build requires a fresh experiment root. Scheduling/reporting updates only need refreshed scripts.

## 4. Test one package when it is ready

**FFTW can be tested as soon as its build finishes and ReFrame is prepared. HDF5 and LAPACK are not prerequisites.** Prepare ReFrame on the login node using the step above. On each compute-node environment, `prepare-tests --check` verifies it without installing or downloading anything; `test` repeats that check automatically.

Run inside a Slurm compute allocation. Replace the account and partition in this example with the site values. After `salloc` grants the allocation, `srun` moves the command shell onto a compute node:

```bash
salloc --account=YOUR_ACCOUNT --partition=YOUR_PARTITION --nodes=1 --ntasks-per-node=1 --cpus-per-task=1 --time=01:00:00
srun --nodes=1 --ntasks=1 --pty bash
export TRIAL_ROOT="$HOME/COMPILER_HARDENING"
"$TRIAL_ROOT/runner/trial" prepare-tests --check
"$TRIAL_ROOT/runner/trial" test fftw
```

The command chooses one CPU from the shell’s allowed CPU affinity, runs the FFTW small/large/planning/startup cases with ten full/reference pairs each, and prints ReFrame results. It writes raw pairs, means, standard deviations, runtime change and confidence intervals below the printed `results/reframe/RUN_ID` directory. Ten pairs are a pilot; use `--pairs 20` and repeat in three separate allocations for the first assessment. Keep host/allocation results separate.

For HDF5, set `IO_DIR` to a dedicated directory on the filesystem you intend to measure, then run `test hdf5`. For LAPACK, run `test lapack`. These commands select only that package’s cases.

For MPI, obtain a two-node allocation with at least one core per node. Start the command shell with `srun --nodes=1 --ntasks=1 --overlap --pty bash`; the [Slurm overlap option](https://slurm.schedmd.com/srun.html#OPT_overlap) permits resource sharing while that command shell occupies a job step. Run:

```bash
export TRIAL_ROOT="$HOME/COMPILER_HARDENING"
"$TRIAL_ROOT/runner/trial" test fftw --mpi --nodes 2
```

MPI testing first checks placement/communication using both private stacks, then measures the selected package. It uses one rank per selected node and records actual placement. `--nodes 1` supports an initial single-node MPI check; it does not establish multi-node behavior. HDF5 MPI uses `test hdf5 --mpi --nodes 2` with `IO_DIR` set to a directory shared by the selected nodes. Run only one measurement command at a time in the allocation.

## Coming back tomorrow

Set `TRIAL_ROOT` and run `"$TRIAL_ROOT/runner/trial" status`. Completed artifacts are verified. Continue with the next build or test command. If pulling more updates, repeat step 1’s installer and step 2’s setup; there is no need to rebuild an unchanged GCC.

`"$TRIAL_ROOT/runner/trial" logs` lists recent step logs. Inspect a printed path with `less /path/to/log`. A failed child command returns an error to your shell and shows where it stopped. Keep interactive `set -e` off.

## Larger campaigns and recipe references

Once individual pilots work, [08 — separate Slurm jobs](08-slurm-campaign.md) runs the full suite across allocations. [10 — one reserved allocation](10-single-allocation.md) is the optional 8/4/2-node controller. These advanced campaign scripts still require their documented site settings and generation steps; `trial test` is the simpler independent-package route. Do not regenerate/rebuild while queued or running campaigns use the trial tree.

| Reference | Purpose |
|---|---|
| [01](01-common.md) | Flag definitions, qualification and paired measurement |
| [00b](00b-openmpi-ucx.md) | UCX/Open MPI recipes and transport qualification |
| [02](02-fftw.md), [03](03-hdf5.md), [04](04-lapack.md), [05](05-parallel.md) | Package recipes and callers |
| [06](06-reframe.md) | ReFrame definitions and report fields |
| [11](11-stack-comparison.md) | Complete-stack experimental scope and later attribution |
| [07](07-consumer-pie.md), [12](12-osu-screen.md) | Optional PIE attribution and OSU communication screen |
| [09](09-results-presentation.md) | Interpretation and presentation |
| [13](13-driver.md) | Driver behavior and embedded source |

## Download for a new trial

The public repository is [ray12514/compiler-hardening-trial](https://github.com/ray12514/compiler-hardening-trial), branch **`main`**.

```bash
mkdir -p "$HOME/COMPILER_HARDENING"
cd "$HOME/COMPILER_HARDENING"
git clone --branch main --single-branch \
  https://github.com/ray12514/compiler-hardening-trial.git compiler-hardening-trial
```

For a machine without Git/network access, download the branch archive on a connected machine and transfer it through the site route:

```bash
curl -fL --retry 3 -o compiler-hardening-trial.tar.gz \
  https://codeload.github.com/ray12514/compiler-hardening-trial/tar.gz/refs/heads/main
sha256sum compiler-hardening-trial.tar.gz > compiler-hardening-trial.tar.gz.sha256
# After transferring both files:
sha256sum --check compiler-hardening-trial.tar.gz.sha256
mkdir compiler-hardening-trial
tar -xzf compiler-hardening-trial.tar.gz --strip-components=1 -C compiler-hardening-trial
```

Stage GCC/package/MPI sources and Python wheels separately as documented in 00/00b/06. Retain the archive/checksum with results. Do not replace an existing checkout by extracting an archive over it.

Workflow verification: Linux GNU compiler probes and ELF checks, rejected-option and unrelated-error fixtures, shell survival, independent dependency selection, artifact reuse checks, retry preservation, and ReFrame 4.10.4 FFTW-only execution with synthetic linked payloads. GNU checks used the lab’s GCC 13 with a test-only version wrapper; no GCC 12.5 build or real package performance is claimed. The target GCC 12.5/Open MPI 4.1.8/UCX builds and campaign still need qualification on the test system.
