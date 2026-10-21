# Standalone compiler hardening trial

Continuing after the October trials? Start with [build verification, the 20-node
batch job and an updateable team summary](15-verification-and-batch.md).

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

Next, follow **step 1 below, including its installer**. This selects the
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
python3 "$RUNBOOK_REPO/scripts/install_driver.py" --trial-root "$TRIAL_ROOT"
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

### If UCX stops while building Go bindings

Missing `bindings/go/src/ucx` or `bindings/go/src/examples/perftest`, followed by
`go.mod`/`no Go files` errors, can occur after the UCX C/C++ libraries and tools
compile. The recipe now passes `--without-go` for both full/reference builds.
It keeps the same UCX version, source checksum, hardening flags and transport
selection; the [UCX recipe](00b-openmpi-ucx.md#3-build-matching-ucx-variants)
explains the optional-binding failure.

After the failed command and any queued trial work have stopped, update the
public checkout and rerun step 1's installer. In the existing compute
allocation/root, resume the interrupted all-package build with:

```bash
"$TRIAL_ROOT/runner/trial" build all --retry
```

The driver preserves the failed UCX attempt under `build/retired/`, configures
a fresh attempt with Go bindings disabled and verifies/reuses unchanged completed
FFTW/HDF5/LAPACK/BLAS artifacts. This recipe-only change needs no repeat of setup
or flag qualification. For an interrupted single-package route, repeat its
original command with `--retry`, such as `build fftw --mpi --retry`.

These retry instructions apply to a failed, driver-recorded UCX attempt. If a
UCX arm or dependent MPI build already completed under different configure
options, retain it and follow the driver's changed-input guidance; do not delete
completion records or relabel the old binaries as the new build.

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

One allocated node is sufficient for compilation and these local package checks.
Allocate enough CPU slots on that node: some upstream checks launch multiple MPI
ranks. FFTW 3.3.11 runs 1/2/3/4 ranks and, with threads enabled here, a
3-rank × 2-thread check; HDF5 allows two ranks. Request at least four MPI slots
and six allocated CPUs for FFTW's complete checks; a one-node allocation with
eight task slots (for example, the site-approved equivalent of
`--nodes=1 --ntasks=8 --cpus-per-task=1`) covers these counts. Inspect the generated
test commands and allocation CPU binding as well. Do not enable oversubscription
to hide a slot shortage. A successful one-node check does not verify inter-node RDMA;
use two nodes for the fabric qualification in step 4.

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

## If parallel HDF5 configuration cannot find MFU

The earlier parallel HDF5 recipe enabled `HDF5_BUILD_PARALLEL_TOOLS=ON`.
In the pinned HDF5 2.1.0 source, that requests additional command-line utilities
and requires MFU (mpi-file-utils), libcircle and DTCMP. The trial's fixed MPI
caller uses the HDF5 library API directly and does not use those utilities.

The corrected recipe sets `HDF5_BUILD_PARALLEL_TOOLS=OFF` for both arms.
Parallel HDF5 remains enabled (`HDF5_ENABLE_PARALLEL=ON`), and the parallel
correctness tests, regular tools and high-level library remain enabled. No MFU
installation is needed for this trial. This does not disable HDF5 MPI support
or skip its correctness tests.

After the failed build and any queued trial work have stopped, update and
refresh the driver snapshot on the login node:

```bash
export TRIAL_ROOT="${TRIAL_ROOT:-$HOME/COMPILER_HARDENING}"
export RUNBOOK_REPO="${RUNBOOK_REPO:-$TRIAL_ROOT/compiler-hardening-trial}"
git -C "$RUNBOOK_REPO" pull --ff-only &&
python3 "$RUNBOOK_REPO/scripts/install_driver.py" --trial-root "$TRIAL_ROOT"
```

Then rerun the existing batch build command in a sufficiently sized allocation:

```bash
"$TRIAL_ROOT/runner/trial" build all --retry
```

For an interrupted `hdf5-mpi-full` configure, the driver retains the failed
attempt and starts that package with a fresh build directory/cache. It verifies
and skips completed FFTW, UCX/Open MPI and other unchanged packages, then
continues HDF5-MPI full/reference. The changed build recipe affects only the
MPI HDF5 package; the compiler profiles, serial HDF5 and FFTW recipes are
unchanged. No new setup/flag qualification is required. Keep existing completion
and pending records; do not patch the old CMake cache or install arbitrary MFU
libraries to bypass this optional dependency.

## If parallel h5diff tests fail with UCX_PREFIX warnings

If `MPI_TEST_H5DIFF-*` fails with `COMPARE Result: 1` and the extra output is
`UCX WARN unused environment variable: UCX_PREFIX`, the warning is contaminating
an exact-output comparison. `UCX_PREFIX` names our installation directory; it
is not a UCX runtime option. This explains that output mismatch, but does not
establish the cause of any other failures in the suite.

The updated driver removes the export attribute from `UCX_PREFIX` after MPI
activation and saved runtime tuning. The path remains available to the build
shell, while MPI programs no longer inherit it. Other UCX warnings, saved
transport/device choices and HDF5 correctness tests remain enabled.

After the failed build and any queued trial work have stopped:

```bash
export TRIAL_ROOT="${TRIAL_ROOT:-$HOME/COMPILER_HARDENING}"
export RUNBOOK_REPO="${RUNBOOK_REPO:-$TRIAL_ROOT/compiler-hardening-trial}"
git -C "$RUNBOOK_REPO" pull --ff-only &&
python3 "$RUNBOOK_REPO/scripts/install_driver.py" --trial-root "$TRIAL_ROOT"
```

Then, in the build allocation with at least two MPI slots available:

```bash
"$TRIAL_ROOT/runner/trial" build all --retry
```

No new setup or compiler qualification is needed. The fix changes runtime
activation in the driver, leaving package recipe identities unchanged. Completed
packages are verified and skipped. The failed HDF5 attempt is archived, then
configured, compiled, tested and installed again; `--retry` does not resume at
CTest. Do not delete completion records or bypass the failed comparisons.

For a manually launched check, use `export -n UCX_PREFIX` after sourcing the
matching `mpi-env*.sh` and runtime tuning file in the same Bash shell. Sourcing
the activation file again restores its export attribute, so repeat the command
after each activation. Avoid globally suppressing unused-variable warnings.

## Recover a completed TCP-only MPI build for RDMA

Use this when the report shows active InfiniBand hardware but UCX was built
without verbs/RDMA-CM. A completed TCP build cannot be repaired by adding runtime
flags or by ordinary `--retry`. Keep the same trial root and qualification;
retire its affected dependency graph explicitly before rebuilding it.

First stop all running and queued trial builds/tests using this tree. On the
login node, with the trial's Python 3.10+ available:

```bash
export TRIAL_ROOT="${TRIAL_ROOT:-$HOME/COMPILER_HARDENING}"
export RUNBOOK_REPO="${RUNBOOK_REPO:-$TRIAL_ROOT/compiler-hardening-trial}"
git -C "$RUNBOOK_REPO" pull --ff-only &&
python3 "$RUNBOOK_REPO/scripts/install_driver.py" --trial-root "$TRIAL_ROOT"
```

In the Slurm build allocation, with the saved site modules/environment available,
inspect the plan first. These commands select the normal system development
headers/libraries and automatic local RDMA device selection:

Your current one-node build allocation is sufficient if it has the intended
fabric visible and enough CPU slots for the package checks described in step 3.
Keep the two-node allocation for the subsequent inter-node verification.

```bash
export TRIAL_ROOT="${TRIAL_ROOT:-$HOME/COMPILER_HARDENING}"
export RUNBOOK_REPO="${RUNBOOK_REPO:-$TRIAL_ROOT/compiler-hardening-trial}"
unset TRIAL_UCX_CONFIGURE_ARGS TRIAL_MPI_TUNING
python3 "$RUNBOOK_REPO/scripts/recover_mpi_rdma.py" --trial-root "$TRIAL_ROOT"
```

Then apply and rebuild:

```bash
python3 "$RUNBOOK_REPO/scripts/recover_mpi_rdma.py" --trial-root "$TRIAL_ROOT" --apply &&
"$TRIAL_ROOT/runner/trial" build all --retry
```

The helper checks completed artifact hashes and qualification, takes the driver
lock and verifies the downloaded MPI/UCX archives. Before moving the old graph,
it compiles and runs a small link probe for verbs/RDMA-CM using the saved GCC
environment. Missing prerequisites stop there with a log, leaving the old graph
in place. Nonstandard installations can be selected with `--verbs-prefix` and
`--rdmacm-prefix` on both the plan and apply commands. Use only the actual site
development prefixes; site-specific runtime library paths must also be available.

Recovery moves the old UCX, Open MPI, FFTW-MPI and HDF5-MPI build/install paths,
callers, environment files and state records for both arms under one
`build/retired/mpi-rdma-<time>/` directory with a recovery manifest. GCC, serial
FFTW/HDF5/BLAS/LAPACK, source downloads, qualification and prior results remain.
The archive preserves old evidence and file mappings; it is not a relocated,
ready-to-run old MPI installation. Preparation errors roll back the moves when
storage allows; an incomplete rollback is reported with its manifest path.
Unmanaged directories, modified completed artifacts and symlinked/external
state require inspection rather than automatic retirement.

`runner/mpi-config.json` saves `--with-verbs --with-rdmacm` and the selected
runtime file for future driver commands, so a new shell does not silently
return to TCP build defaults. The default runtime file selects `rc,sm,self` and
lets UCX choose available RDMA devices. For an already qualified site-specific
runtime file, pass `--tuning-file /absolute/path/to/file` when applying recovery.
Conflicting exported build/runtime selections fail explicitly. Repeating the
same recovery after it is recorded preserves progress and tells you to resume.

The rebuild verifies/reuses completed serial artifacts and creates both full and
reference UCX/Open MPI/MPI payloads. A requested RDMA UCX arm must expose an RC
transport on the build node before the driver records it complete. Run in an
allocation with the intended fabric visible. This is a local capability check;
finish with the two-node MPI verification in step 4 before accepting timings.
The driver now reapplies selected runtime tuning after each arm's activation
for verification, package build helpers and ReFrame execution.

If `ompi_info` still warns about missing optional-component libraries, keep the
diagnostic report identifying the affected components. Correct required library
paths/dependencies before qualification; do not infer that every warning is the
cause of a UCX PML failure or suppress it without checking. The collector now
includes `ompi_info --all` diagnostics for this purpose.

## Collect MPI and fabric diagnostics

Use this when an MPI/UCX verification fails or before choosing a site's fabric
settings. The collector finds the full/reference prefixes through the saved
`mpi-env*.sh` files and uses the documented installation layout when an arm is
incomplete. It records versions, UCX transports/devices, RDMA port state,
memlock, UCX PML library resolution, build flags and recent MPI error logs.

On the login node, update the source checkout on the shared filesystem:

```bash
export TRIAL_ROOT="${TRIAL_ROOT:-$HOME/COMPILER_HARDENING}"
export RUNBOOK_REPO="${RUNBOOK_REPO:-$TRIAL_ROOT/compiler-hardening-trial}"
git -C "$RUNBOOK_REPO" pull --ff-only
```

Then, in the allocated compute-node shell where the error occurred, with its
normal site modules loaded:

```bash
export TRIAL_ROOT="${TRIAL_ROOT:-$HOME/COMPILER_HARDENING}"
export RUNBOOK_REPO="${RUNBOOK_REPO:-$TRIAL_ROOT/compiler-hardening-trial}"
python3 "$RUNBOOK_REPO/scripts/collect_mpi_diagnostics.py" --trial-root "$TRIAL_ROOT"
```

No driver reinstall is needed for this diagnostic command. It uses Python's
standard library and runs no MPI jobs, downloads or rebuilds. Saved activation
and any selected tuning file run in child shells; the calling shell is unchanged.
Missing optional tools or incomplete installations are recorded in the report.
The only new files are the reports under
`$TRIAL_ROOT/results/diagnostics/mpi-<time>-<host>-<unique>/`. The command prints
the exact `report.txt` path to share; `report.json` retains full device output.
Run on each selected compute-node type/host as needed. Inventory does not prove
multi-node connectivity or qualify a performance result.

### FFTW MPI check hangs or reports a UD QP permission error

If `make check` stops updating after an MPI command such as `mpirun -np 2`,
the driver's `still running` message means it is waiting for its child process.
It does not establish that the test is making progress. The first ten passing
checks do not establish that the later multi-rank check passed. In
[FFTW 3.3.11's upstream MPI checks](https://github.com/FFTW/fftw3/blob/fftw-3.3.11/mpi/Makefile.am),
the `1 CPU` success message precedes the `-np 2` command; the suite continues
with three/four ranks and, in this threaded build, three ranks with two threads
each. Step 3 gives the full allocation requirement. A two-rank probe below needs
only two slots and is deliberately smaller.

For a stuck foreground build, press Ctrl-C in the terminal running the driver;
Ctrl-C in a `tail -f` terminal only stops the log viewer. For a batch build,
identify and cancel that build job through Slurm. Do not cancel an unrelated job
or delete the trial root/state. Confirm the old build/MPI processes and any
associated Slurm steps have stopped before starting a new attempt. Retain the
allocation if possible; one node with two allocated MPI slots is enough for the
following startup diagnostic.

Keep `mpirun` from the private Open MPI inside the allocation. The UCX selection
is `pml=ucx`, not a replacement launcher. Direct `srun` application launch needs
separately qualified site PMI/PMIx integration; changing launcher is not a fix
for a verbs queue-pair failure. See [Open MPI v4 Slurm integration](https://www.open-mpi.org/faq/?category=slurm).

An `error initializing an OpenFabrics device` warning can originate in the old
`openib` BTL even when the UCX PML is selected. Selecting UCX alone does not
disable that BTL. A separate [upstream report](https://github.com/easybuilders/easybuild-easyconfigs/issues/20233)
of `Failed to modify UD QP to INIT ... Operation not permitted` identified OFI/
libfabric component probing. These are diagnostic leads, not proof of this
site's cause. UCX/device permissions, driver/firmware compatibility and the
actual linked libraries still require checking if the error persists.
[Open MPI's OpenFabrics FAQ](https://www.open-mpi.org/faq/?category=openfabrics#ofa-device-error)
explains why disabling the old `openib` BTL leaves UCX's fabric support available.
Do not rebuild UCX without verbs or hide warnings to make a test appear to pass.

After the old attempt has stopped, update the checkout on the connected login
node, then run the inventory collector above on the affected compute node. No
driver reinstall is needed for this standalone startup probe. In that same
allocated compute-node shell:

```bash
export TRIAL_ROOT="${TRIAL_ROOT:-$HOME/COMPILER_HARDENING}"
export RUNBOOK_REPO="${RUNBOOK_REPO:-$TRIAL_ROOT/compiler-hardening-trial}"
python3 "$RUNBOOK_REPO/scripts/probe_mpi_startup.py" --trial-root "$TRIAL_ROOT" --arm full --mode saved
```

This compiles a tiny diagnostic with the selected private `mpicc`, then launches
two ranks on the current allocated host using its private `mpirun`, explicit
`pml=ucx`, no oversubscription and the saved runtime tuning. It prints markers
before/after `MPI_Init`, checks a collective, and requires both ranks to finish.
Each compile/startup step is limited to 45 seconds, followed by up to three
seconds for local process cleanup. It preserves output and exact commands under
`results/diagnostics/mpi-startup-*`; it changes no build state or saved tuning.
It refuses an active driver lock or a host outside the allocation. Slurm steps
can still require operator cleanup after a broken launcher; inspect them after
a timeout before launching another probe.

If an earlier probe reports `not enough slots`, it failed before the application
could initialize MPI. That result does not test UCX/OpenFabrics or show that the
MPI build is broken. The probe now uses `--host node:2`; the previous bare
`--host node` could cap the host at one slot even when Slurm advertised more.
This correction retains Slurm's resource limit. The report and terminal now
include Slurm task/CPU variables and the calling shell's allowed CPU affinity.

Open MPI also reads Slurm's task counts, so an interactive `srun -n 1` shell can
advertise one MPI slot even when the job reserved more CPUs. For this short
startup diagnostic only, explicitly allow two ranks to share the available
slots/CPUs if needed:

```bash
python3 "$RUNBOOK_REPO/scripts/probe_mpi_startup.py" --trial-root "$TRIAL_ROOT" --arm full --mode no-openib-ofi --oversubscribe
```

This selects `--oversubscribe --bind-to none` for this probe and records that
choice. It does not request more Slurm resources, remove cgroup limits, change
saved settings or qualify a performance run. Slurm `--overlap` controls sharing
between job steps and is a separate option. A nested launcher waiting for Slurm
step resources is a different failure from a slot-count rejection. Use a batch
allocation sized as in step 3 for the full suite; the batch shell avoids an
extra interactive shell step. Do not fake Slurm resource variables or infer
usable MPI slots solely from the node's physical CPU count.

The probe always prints and executes absolute private `mpicc`/`mpirun` paths.
The inventory collector also records what `mpirun`/`mpicc` resolve to after saved
activation, FFTW's configured `MPIRUN`/`MPICC` values, and the MPI bench's loaded
libraries when its binary exists. FFTW upstream checks can invoke `mpirun` by
name; that resolution must agree with the intended private MPI. An absolute
launcher alone does not rule out a mismatched runtime library or component.
Inspect this evidence before unloading modules, since site modules may also
supply required Slurm/fabric libraries. Do not change the saved module/toolchain
environment while a build is running.

If startup fails or warns, compare component selections one at a time:

```bash
python3 "$RUNBOOK_REPO/scripts/probe_mpi_startup.py" --trial-root "$TRIAL_ROOT" --arm full --mode no-openib
python3 "$RUNBOOK_REPO/scripts/probe_mpi_startup.py" --trial-root "$TRIAL_ROOT" --arm full --mode no-openib-ofi
```

`no-openib` sets the diagnostic BTL selection to `^uct,openib`.
`no-openib-ofi` additionally excludes the OFI BTL and MTL, using
`btl=^uct,openib,ofi` and `mtl=^ofi`. Compare the logs as well as exit status:
warning disappearance and successful startup are separate observations. These
overrides are diagnostic only; the report retains the original saved settings
and each actual command. For a failing reference arm, use `--arm reference`.
If even the isolated selection fails, share its complete `startup.log`, the
probe's `report.json`, and the inventory report before another rebuild.

An earlier GPU/LAMMPS launch example used `btl=self,vader`, `mtl=^mxm`, and
`opal_common_ucx_opal_mem_hooks=1`. For a controlled comparison of its BTL choice,
run the same probe with `--mode local-btls`. This still forces the UCX PML;
its network path is separate from the BTL selection. The photo's command alone
does not prove which fabric carried its traffic. Excluding `mxm` does not
exclude OFI. The memory-hooks option addresses UCX memory-unmap handling, a
different issue documented in [Open MPI's memory-hooks report](https://github.com/open-mpi/ompi/issues/9859);
it is not evidence of a fix for a QP permission failure. Leave GPU/compiler
settings out of this CPU-only trial and test memory-hook changes separately
only when its actual warning or site guidance calls for them.

### Continue package builds after startup passes

The startup probe is a separate diagnostic, not an FFTW installation or a
completion record. The FFTW-MPI build runs in this order: configure/compile,
`make check`, `make install`, compile the fixed caller, then save the completion
record. A stop in `make check` therefore leaves that attempt incomplete before
installation. Other completed serial/MPI prerequisites remain installed.

After all old builds and queued trial work have stopped, pull the public checkout
and run step 1's installer on the login node. The updated driver applies saved
runtime selections after each arm's activation. Then, in the compute-node
environment where startup passed, save its component choices and inspect state:

```bash
export TRIAL_ROOT="${TRIAL_ROOT:-$HOME/COMPILER_HARDENING}"
export RUNBOOK_REPO="${RUNBOOK_REPO:-$TRIAL_ROOT/compiler-hardening-trial}"
python3 "$RUNBOOK_REPO/scripts/apply_mpi_startup_selection.py" --trial-root "$TRIAL_ROOT" &&
unset TRIAL_MPI_TUNING &&
"$TRIAL_ROOT/runner/trial" status
```

The helper requires the latest startup report to have passed and to match the
current private MPI/fabric settings. `--report /absolute/path/to/report.json`
selects a specific passing report instead. It creates a new runtime file that
sources the previous file, then applies only the tested PML/BTL/MTL component
choices. It preserves the UCX build selection, recovery manifest, old runtime
file and build records. It does not copy the diagnostic's `--oversubscribe` or
`--bind-to none` options. The new selection is saved in `runner/mpi-config.json`
for both arms. The final `unset` drops any old exported file selection so later
driver commands use that saved configuration. A repeated application is
idempotent; a failed or mismatched report is rejected without changing settings.

In `trial status`, `fftw-mpi-full: complete; artifacts verified` confirms that
the driver has installed and recorded that arm and caller. An `incomplete`
record means it still needs the build/check/install workflow. Do not infer
completion from a library filename alone, delete pending records, or manually
run `make install` to bypass the failed checks.

For the complete continuation, submit a batch job with the site's normal
account/partition/time settings, one node and enough task/CPU slots as in step 3.
Export `TRIAL_ROOT` to that job and run the driver directly in its batch shell:

```bash
"$TRIAL_ROOT/runner/trial" build all --retry
```

This verifies/skips completed packages. It archives and rebuilds an interrupted
package from configure onward, including upstream checks and installation; it
does not resume at one individual check. Each package completes its full arm,
then its reference, with matching dependencies built as required. If the stop
was `fftw-mpi-full`, that arm must finish before FFTW-MPI reference and the
remaining HDF5-MPI work can complete. `build fftw --mpi --retry` limits the work
to FFTW and its MPI prerequisites if that is the intended scope.

Keep the upstream correctness checks. The startup probe saves repeating them
during diagnosis and does not replace their coverage. After `build all` finishes,
run `trial status` again before moving to the separate ReFrame/performance step
and the two-node RDMA verification. A local startup PASS is not fabric or timing
qualification.

### Settings that belong to each system

| Setting | When to select it |
|---|---|
| `TRIAL_ROOT` | Set once to the existing trial's absolute path; keep the same shared path on login and compute nodes. |
| `RUNBOOK_REPO` | Set to the public checkout; its folder name does not change build state. |
| Required site modules and library/header locations | Use the site's supported setup before configuration and execution; retain those choices with the results. |
| `TRIAL_UCX_CONFIGURE_ARGS` | Choose before UCX builds. For the intended RDMA trial, select compatible verbs/rdmacm support and any required prefixes; the driver default is TCP/shared-memory bring-up. |
| `UCX_TLS` and optional `UCX_NET_DEVICES` | Qualify the transport and usable local device/port on allocated compute nodes. Do not copy an example `mlx5_0:1` blindly between systems. |
| `TRIAL_MPI_TUNING` | Optional absolute path to qualified site runtime settings. RDMA recovery saves its selection in `runner/mpi-config.json`; the driver and collector reapply it after activation. Timed result settings still need checking against qualification evidence. |
| RoCE GID/traffic class, InfiniBand service level and similar tuning | Set only when required and supplied by the site; leave unspecified values at the qualified defaults. |
| Slurm account, partition/constraint, walltime and test scales | Select for the site and campaign. Allocation size alone does not define a sweep. |
| `IO_DIR` / `SHARED_IO_DIR` | Choose the actual measurement filesystem, shared across MPI nodes for the I/O cases. |

Keep system-specific paths and device choices in the saved site configuration
and evidence, rather than editing the general recipe for each machine. Use the
[UCX/RDMA procedure](00b-openmpi-ucx.md#2-select-the-ucx-transport-prerequisites)
to interpret the report before changing completed build inputs. This section
is the current diagnostic procedure; future fixes update it in place rather
than adding a separate competing update guide.

## Qualify an existing multi-node allocation before the sweep

Use this first when the builds have finished and an interactive allocation is
already available. Keep the allocation; do not submit another eight-node job.
Update the checkout while no trial work is running:

```bash
export TRIAL_ROOT="${TRIAL_ROOT:-$HOME/COMPILER_HARDENING}"
export RUNBOOK_REPO="${RUNBOOK_REPO:-$TRIAL_ROOT/compiler-hardening-trial}"
git -C "$RUNBOOK_REPO" pull --ff-only
```

Stop if the pull fails. This standalone helper uses the existing saved MPI
activations/runtime configuration; it needs no driver reinstall, setup or
package rebuild. Run from an allocated compute-node shell, with the site's
required modules loaded:

```bash
"$TRIAL_ROOT/runner/trial" status &&
python3 "$RUNBOOK_REPO/scripts/qualify_test_allocation.py" --trial-root "$TRIAL_ROOT" \
    --slurm-overlap
```

This communication gate does not require ReFrame. Before the subsequent package
pilots, run `"$TRIAL_ROOT/runner/trial" prepare-tests --check`; if it is not
prepared, use the existing `prepare-tests` staging procedure. `status` verifies
the recorded build artifacts; the exact
effective compiler flags remain in `runner/qualification.json`. The new
communication caller is a diagnostic compiled with `-O0`, not a performance
measurement of those flags.

The helper prints the full allocated host list and selects its first two hosts.
For **each** private full/reference stack it runs two bound ranks locally, then
one rank on each selected node. Every rank records its CPU affinity, memlock,
available RC transports, port inventory and private caller/launcher/UCX component
library paths before verifying a 512 KiB ring exchange and an MPI reduction.
The local run exercises intra-node communication; only the inter-node run tests
the network. `UCX_TLS` must already select `rc` (or `rc_mlx5`/`rc_verbs`) with
optional `sm,self`; TCP fallback is rejected. The helper keeps saved PML/BTL/MTL
choices, removes `UCX_PREFIX` from the process environment, and enables UCX info
logging only for qualification. It does not change tuning or build state.

Both participating nodes need at least two allocated core/slot resources for
the local check. A launch/slot/binding failure stops the sequence; inspect the
evidence rather than adding oversubscription to a measurement run. Each compile
or launch is bounded to 90 seconds by default. Slurm's resource-holding
interactive step can affect nested launches. The `--slurm-overlap` option above
adds `--overlap` to Open MPI's actual `srun` launch steps through
`--mca plm_slurm_args`, preserving any existing custom Slurm arguments.
This permits sharing the interactive shell's step resources; it is separate
from Open MPI rank-slot oversubscription. Rank binding and
`--nooversubscribe` remain in effect. Omit `--slurm-overlap` in an ordinary batch
shell with no resource-holding interactive step. This option changes only this
qualification process, not saved MPI settings or later campaign launches.
This is why placement and launch behavior are qualified in this actual
allocation first. See the
[Slurm interactive-step guidance](https://slurm.schedmd.com/faq.html) and
[UCX transport selection](https://openucx.readthedocs.io/en/master/faq.html#selecting-networks-and-transports).

The final path is `results/diagnostics/mpi-allocation-*/report.json`.
Each arm's `local/` and `inter-node/` directories retain `communication.log`
(including bindings and UCX information) and a `rank-N.json` for each rank.
Keep those detailed system records local. To print a summary suitable for
sharing, including for a report produced by an older helper, run:

```bash
python3 "$RUNBOOK_REPO/scripts/qualify_test_allocation.py" \
    --trial-root "$TRIAL_ROOT" --summary
```

This reads the latest saved qualification report and prints only fixed status
fields, counts, return codes, timeout flags and recognized rank stage markers.
It does not launch MPI, change state, or print hostnames, job IDs, addresses,
installation paths, commands or raw errors/log text. `--summary /path/to/report.json`
selects a specific report. Share only that summary before the long campaign.

For new runs, stage markers are flushed before dependency commands, before/after
`MPI_Init`, after data exchange/reduction, and around `MPI_Finalize`. The helper
also prints the safe summary automatically when a run completes or fails.
An empty old log with `no_rank_start_observed` means there is no rank startup
evidence; it does not establish a UCX or compiler failure. A negative return code
after `timed_out: true` can be from the helper terminating the launcher.
If the original run omitted overlap and timed out with no rank startup evidence,
try the same qualification once with `--slurm-overlap` and compare summaries.
Keep hosts, rank counts and fabric settings unchanged. If overlap does not change
progress, use the recorded rank stages to locate the stall rather than repeatedly
rebuilding packages or extending timeouts.

A PASS covers only these hosts/layouts and communication checks; it is neither
an overhead estimate nor qualification of the other six hosts.

To choose a different allocated pair, use `--hosts nodeA,nodeB` with names from
the printed list. A later `--ranks-per-node 4` check uses four bound ranks per
selected node and requires corresponding allocated resources. Four ranks per
node across eight nodes means 32 ranks, whereas one rank per node means eight;
the latter is an inter-node baseline, not the intended limit of the experiment.

After this gate, run short full/reference package pilots from step 4, inspect
durations and variation, then prepare the automated single-allocation campaign
in [10](10-single-allocation.md). That controller runs serial cases on every
host and MPI scales on rotated disjoint groups. It is not an exhaustive set of
all host combinations. Keep host/group/round and rank layouts distinct in the
analysis; repeat rounds within these eight nodes do not count as new allocations.
Choose a production-like rank layout and adequate workload sizes before the
long sweep, using the pilot to budget the remaining allocation time. Do not
assume a twelve-hour reservation makes every optional case necessary or feasible.

## Builds complete and MPI qualified: run the package pilot

**This is the next step after both stacks pass local/inter-node qualification.**
The communication diagnostic is finished; this stage measures the actual
prebuilt FFTW, HDF5 and LAPACK callers against their matching reference stacks.
Stay in the existing allocation. The bootstrap, new-trial download and
"coming back tomorrow" sections are not additional prerequisites.

First update the installed driver and refresh its measurement scripts while
no trial command is running:

```bash
export TRIAL_ROOT="${TRIAL_ROOT:-$HOME/COMPILER_HARDENING}"
export RUNBOOK_REPO="${RUNBOOK_REPO:-$TRIAL_ROOT/compiler-hardening-trial}"
git -C "$RUNBOOK_REPO" pull --ff-only &&
python3 "$RUNBOOK_REPO/scripts/install_driver.py" --trial-root "$TRIAL_ROOT" &&
"$TRIAL_ROOT/runner/trial" refresh-tests &&
"$TRIAL_ROOT/runner/trial" prepare-tests --check
```

`refresh-tests` regenerates only the paired harness, ReFrame definitions and
rank guards after verifying the recorded environment/profile/qualification.
It preserves completed packages, their identities and compiler qualification.
No compiler probes, package builds or downloads run. If ReFrame is not prepared,
use the existing `prepare-tests` login/staging procedure and return here.

Set `IO_DIR` locally to a **dedicated directory on the shared filesystem you
want HDF5 to measure**. Both MPI nodes need access at the same absolute path.
Keep the private path local; it is not needed to share the headline results.
For example, replace the placeholder with the actual scratch path:

```bash
export IO_DIR=/YOUR/SHARED/SCRATCH/hardening-package-pilot
```

For the interactive allocation where Slurm overlap passed qualification:

```bash
"$TRIAL_ROOT/runner/trial" test all --pairs 10 --nodes 2 \
    --ranks-per-node 4 --slurm-overlap
```

This is a short **all-package pilot**, not the full host/scale campaign.
It runs the following five sessions sequentially and stops after a failure:

| Session | Pilot coverage |
|---|---|
| Serial FFTW | Small/large transforms, planning and startup |
| Serial HDF5 | Contiguous/chunked I/O and startup |
| Serial LAPACK | Small/large solves and startup |
| MPI FFTW | Small/medium transforms and planning |
| MPI HDF5 | Collective/independent I/O and small data |

There are 16 workload/comparator cases, each with warmups and ten alternating
full/reference process pairs. Serial cases use an allowed CPU on the current
compute host. MPI cases use the first two allocated hosts, four bound ranks per
node (eight total), with matching full/reference MPI/UCX and saved component
choices. This needs four allocated cores/slots per participating node; placement
checks run before timing. `--ranks-per-node 1` selects the qualified inter-node
baseline instead. `--slurm-overlap` reaches both the placement probes and the
timed private `mpirun` launches; it shares the interactive step resources and
does not enable MPI rank oversubscription. UCX info logging is off during timing.

The driver prints the primary full/reference runtime changes and intervals, and
the pilot directory under `results/pilots/`. That directory contains:

- `pilot.json`: planned sessions, elapsed seconds, completion/failure status,
  links to ReFrame sessions and missing-workload coverage.
- `phases.csv`: one row per completed workload and timing phase, including
  full/reference means and standard deviations, runtime change, interval bounds,
  node/rank layout, effective profile IDs and the source summary reference.

Every session also retains ReFrame reports, raw paired CSV, summary JSON,
dependency evidence and driver logs under its linked `results/reframe/` path.
Partial CSV and coverage records are written even if a later session fails;
missing cases are not zero-overhead results. These are real measurement inputs
for spreadsheet/Python plotting; no plot is generated or benchmark value invented
by the pilot command.

Inspect correctness, completeness, runtimes and variability before the larger
campaign. Positive runtime change means full was slower; intervals crossing zero
leave the direction unresolved. The next campaign expands to serial cases on
every node, additional workloads and selected MPI host groups/scales through
[10](10-single-allocation.md). Its rounds and rank layouts remain separate
conditions, rather than one pooled average. Choose its runtime budget using
the pilot's recorded durations. Skip to step 4 below only when testing one
package independently.

## Next session: fixed-caller application-pattern assessment

Today's package pilots and dense results remain valid records of the matched
caller-and-stack comparison. The [session report](../../output/pdf/compiler-hardening-session-report-2026-10-16.pdf)
is provisional until the original paired data have been reviewed. The next
question is deployment: **does an ordinarily compiled caller change performance
when it uses our hardened libraries?** This phase uses the existing FFTW/HDF5
harness; it does not require building a complete application or adding an
unrelated package.

1. Preserve the original result directories. Review paired timings, intervals,
   work sizes, actual I/O modes and build records; keep different allocations,
   layouts and partial conditions separate.
2. Pull and reinstall the driver using the commands below. Keep the completed
   full/reference packages. The new workload source gets a new caller identity;
   it does not overwrite old callers or rerun package builds. Existing profile
   and package recipe blocks are unchanged; `refresh-tests` is not needed for
   this production-only update.
3. In the next compute allocation, audit its usable physical cores and service
   reservations. Run a short, fixed-work deployment pilot through ReFrame.
4. Review correctness, actual bindings/library paths, achieved timing precision
   and memory/I/O cost. Then increase density and scale in bounded runs. Agree
   on the meaningful overhead limit before confirmation sampling; repeat
   selected conditions in an independent allocation.

```bash
export TRIAL_ROOT="$HOME/COMPILER_HARDENING"
export RUNBOOK_REPO="$TRIAL_ROOT/compiler-hardening-trial"
git -C "$RUNBOOK_REPO" pull --ff-only
python3 "$RUNBOOK_REPO/scripts/install_driver.py" --trial-root "$TRIAL_ROOT"
"$TRIAL_ROOT/runner/trial" prepare-tests --check
```

Inside the allocation, keep the existing shared `IO_DIR`. The first candidate
uses three persistent fields, reused measured plans, 32 iterations, and a
checkpoint every eight iterations. These are explicit starting parameters, not
a claim to reproduce an identified CFD or LAMMPS input. Change them to match the
chosen site's transform sizes, field count and checkpoint cadence before the
confirmation run.

```bash
: "${IO_DIR:?Keep IO_DIR set to the dedicated shared trial I/O directory}"
"$TRIAL_ROOT/runner/trial" production --audit-only \
  --nodes 1,2 --ranks-per-node 16 --slurm-overlap

"$TRIAL_ROOT/runner/trial" production --scope deployment --reframe \
  --nodes 1,2 --ranks-per-node 16 --shape 256,256,256 \
  --fields 3 --fft-plan measure --steps 32 --checkpoint-every 8 \
  --pairs 4 --budget-minutes 60 --slurm-overlap
```

Use node scales that actually fit the allocation. In the interactive session
that required overlap, retain `--slurm-overlap`: this reaches Open MPI's
internal Slurm launch and the inventory `srun`. It is not MPI oversubscription.
The audited WEKA exclusions, one rank per selected physical core and no TCP
data fallback remain enforced. Add an operator-verified reservation override
only if discovery needs it, using the same override on both commands.

`--scope deployment` compiles **one reference caller once** and uses that exact
executable and SHA-256 for both arms. The selected complete FFTW/HDF5/MPI/UCX
stack changes through its runtime library paths. Every rank checks the caller
hash and intended loaded-library paths. The same source versions and compatible
interfaces are required. Header/inlined code remains that of the reference
caller. `--scope stack` preserves the original matched-callers comparison.

The driver verifies completed package artifact hashes and writes
`artifact-evidence.json`: effective profile vectors, observed RELRO/NOW and
canary/fortified-call symbols in installed DSOs. Requested linker protections
must be present. A DSO without a fortified or canary symbol is not automatically
unhardened: compiler decisions and function coverage can legitimately leave
none. This evidence does not measure protection coverage of every function.

`--fields` applies to FFT and standalone I/O: each persistent field has its own
forward/inverse plans, and each checkpoint writes one dataset per field. FFT
volumes and standalone I/O MiB targets are **per field, per rank**; memory and
checkpoint/write budgets count all fields. The three-field example performs
six global transforms per iteration; ranks are not extra independent samples.
Measured planning is recorded separately and plans are reused during timing.
Final numerical checks and checkpoint read-back remain outside loop timing.
Dataset layout is still contiguous and checkpoints replace a single file; this
does not cover chunked/compressed output, retained-file history, cold reads or
every application I/O pattern.

ReFrame runs one allocation-local controller check with serial execution,
retaining the controller's CSV/JSON/HTML plus per-condition performance values
in `results/production-reframe/TIMESTAMP/report.json`. Its `campaign.json`
points to the underlying `results/production/` directory. There is no second
timing harness. A budget-partial campaign is retained and **does not pass** the
ReFrame completion check. Direct `production` runs still retain partial data
without treating budget exhaustion as a numerical failure.
ReFrame JSON/job output may contain private host information; use the
controller's metric-only CSV/HTML for sharing.

After reviewing that pilot, a candidate density run is:

```bash
"$TRIAL_ROOT/runner/trial" production --scope deployment --reframe \
  --nodes 1,2 --ranks-per-node all --fields 3 --fft-plan measure \
  --fft-mib-per-rank 2 --io-mib-per-rank 2 \
  --steps 32 --checkpoint-every 8 --pairs 10 \
  --budget-minutes 90 --slurm-overlap
```

This second command uses volume per rank rather than the first command's fixed
global shape. Keep those experiments separate. After its costs are known,
run `--nodes 4` and `--nodes 8` separately with the chosen frozen work definition;
do not place the largest, still-missing condition last behind a broad sweep.
Explicit shapes must satisfy the supported balanced slab constraints at every
requested rank count. This distributed complex-FFT harness is a controlled
application-pattern proxy, not LAMMPS PPPM's complete local-FFT/remap workflow.

For confirmation, select an even pair count such as `--pairs 20` and set
`--overhead-limit-percent` to the agreed limit. No acceptance limit is guessed
by default. Reports distinguish `within_limit` (upper interval bound at or below
the limit), `above_limit` (lower bound above it), `unresolved`, `incomplete` and
`not_declared`. A within-limit result applies only to that completed condition;
independent-allocation confirmation and deployment scope still matter. Fixed
`--steps` is never silently reduced to fit a write budget; insufficient budget
retains an explicitly partial campaign. Do not multiply a percent effect by
node or iteration counts. CSV includes seconds per iteration and transform
counts as well as observed whole-loop and whole-launch times.

### Optional OSU baseline

Include a small CPU-only OSU Micro-Benchmarks baseline to separate MPI behavior
from the FFT/I/O workflow: `osu_latency` and `osu_bw` with exactly two ranks
(one per node), then `osu_alltoall` and `osu_allreduce` at the qualified workload
density. A two-rank point-to-point test is not a dense-network saturation test;
`osu_mbw_mr` can be a later bounded addition if concurrent-pair behavior needs
explanation. OSU's internal iterations are not independent process pairs.

Use a pinned released OSU version, one ordinarily compiled executable per
benchmark, and the compatible full/reference Open MPI/UCX stacks. Keep message
sizes and OSU warmup/iteration settings identical, record version/build identity,
binding and loaded libraries, and bound collective buffers against rank count
and available memory. Report bandwidth in its original units (higher is better)
and latency separately (lower is better); do not label bandwidth change as
runtime overhead. No MVAPICH installation is required to use the MPI benchmarks
with Open MPI. The automated adapter is now available as `trial osu prepare`,
`trial osu build` and `trial osu test --reframe`. Download or import the
hash-pinned source on the login node first; the four ordinary callers can then
be built offline on the login or a compute node. **Finish the next fixed-caller
FFTW/HDF5 test first**, then pass its completed production result directory to
OSU with `--after-production`. Matching MPI/UCX build identities are checked.
It remains a separate follow-up and does not block or replace FFTW/HDF5.
Use the [automated OSU run sequence](12-osu-screen.md) for copy-and-paste commands,
matrix settings and exports.
[Official OSU benchmark descriptions](https://mvapich.cse.ohio-state.edu/benchmarks/)

## After the pilot: run production-density workloads

The low-rank package pilot establishes runnable full/reference comparisons.
The next assessment must also exercise the cores allocated to a production job,
sustained FFT communication, distributed checkpoint I/O and repeated work inside
a long-lived process. The existing one-/four-rank layouts and small datasets
are screening cases; increasing only their node count does not provide that
coverage.

Use **`trial production`** for this stage. It reuses the completed libraries and
compiles new callers under separate identities. Its default `--scope stack`
uses matched callers; `--scope deployment` uses one fixed reference caller.
It does not rebuild
packages or replace the existing pilot callers. Package pilots still use
ReFrame; the production controller launches sustained callers with the private
`mpirun` and exports CSV/JSON plus an offline HTML dashboard. Add `--reframe` to
run that same controller through ReFrame, as in the next-session workflow above.

Wait for the current trial command to finish, then update the installed driver:

```bash
export TRIAL_ROOT="$HOME/COMPILER_HARDENING"
export RUNBOOK_REPO="$TRIAL_ROOT/compiler-hardening-trial"
git -C "$RUNBOOK_REPO" pull --ff-only
python3 "$RUNBOOK_REPO/scripts/install_driver.py" --trial-root "$TRIAL_ROOT"
```

First audit the **existing allocation**; no package build or measurement runs:

```bash
"$TRIAL_ROOT/runner/trial" production --audit-only \
  --nodes 2,4,8 --ranks-per-node 16,32,all --slurm-overlap
```

`--nodes` lists the scales to test, not a new allocation request. On another
allocation choose scales that fit. The audit checks every allocated host by
default. It discovers the job's effective CPU grant, physical-core topology and
WEKA's narrow cgroup masks and/or documented `weka local resources` core table.
Job cpuset cgroups are used when available. On task/affinity-only sites or when
the job ancestor is hidden, it requests one dedicated inventory task per host,
bound by Slurm to that host's allocated CPU count. It accepts the fallback only
when task/affinity is configured, Slurm reports binding, and the observed CPU
mask matches the requested full-capacity count. An ordinary interactive shell
mask is never used for this fallback. Rank-slot limits are applied separately
after service-core exclusions; 92 task slots do not mean a 96-CPU grant must be
cut to an arbitrary 92-CPU mask before discovering WEKA's cores.
It excludes reserved cores and their SMT siblings and uses one hardware thread
per core. It also checks Slurm CPU/task capacity separately. With 96 physical
cores and 92 allocated slots, `all` can mean 92 **only if** 92 safe cores are
actually granted. If the job's 92-CPU mask still includes four WEKA cores,
`all` means 88; the other hardware cores cannot be reclaimed outside the grant.
Each group uses the smallest verified per-node capacity for an equal layout.

If WEKA's reservation cannot be resolved, the audit stops and retains its log.
Inspect the local client resource assignments and effective cgroup masks; do not
send the full system inventory or assume the tentative 19–22 range. After
verifying **OS CPU IDs** on every selected node, use `--reserved-cpus VERIFIED_LIST`
for an identical reservation, or `--reservations /absolute/private/reservations.json`
for a JSON object mapping each short hostname to its CPU-list string. Supply
the same option to both the audit and measurement commands. `--reserved-cpus none`
is an explicit assertion for systems with no service-core reservation.
[WEKA allocation guidance](https://docs.weka.io/best-practice-guides/weka-and-slurm-integration/avoid-conflicting-cpu-allocations)

For `Cannot locate this Slurm job cgroup`, pull and reinstall the updated driver
using the commands above, then repeat the audit. No package rebuild, new
allocation or Slurm/WEKA configuration change is needed to try the updated
discovery. The fallback still stops if a CPU grant cannot be verified.

To locate WEKA's cores independently of the Slurm check, run on a compute node:

```bash
python3 "$TRIAL_ROOT/runner/production/placement.py" --show-weka
```

This prints only discovered OS CPU IDs. Common cgroup v1 files are
`/sys/fs/cgroup/cpuset/weka-client/cpuset.cpus` and `cpuset.effective_cpus` in the
same directory. A common v2 path is
`/sys/fs/cgroup/weka.slice/cpuset.cpus.effective`; actual paths vary. The helper
searches WEKA-named cgroups and the local resources table rather than assuming
those example paths. These files identify WEKA's reservation, not Slurm's grant.
[Slurm binding documentation](https://slurm.schedmd.com/srun.html#OPT_cpu-bind)

After the audit passes, keep your existing **`IO_DIR`** pointing at the dedicated
shared trial directory on the filesystem to measure. Run the first dense stage:

```bash
: "${IO_DIR:?Keep IO_DIR set to the existing shared trial I/O directory}"
"$TRIAL_ROOT/runner/trial" production --nodes 2 --ranks-per-node 16 \
  --pairs 10 --target-seconds 30 --budget-minutes 90 --slurm-overlap
```

This runs four conditions: sustained forward/operator/inverse FFT with reused
plans; repeated collective HDF5 checkpoints; repeated independent HDF5
checkpoints; and an FFT loop with a checkpoint every four iterations. Both
stacks first pass communication qualification at the requested density. Each
condition preflights FFT slab sizes, memory and storage, calibrates both arms,
freezes equal iteration counts and uses balanced randomized full/reference
process-pair order. All numerical libraries and OpenMP use one thread per rank.

MPI uses `mpirun --nooversubscribe`; a rank wrapper applies the explicit per-host
OS CPU binding and verifies it before executing the caller. Open MPI's own
binding is disabled to avoid mixing its logical indexes with OS CPU IDs.
`--slurm-overlap` reaches Open MPI's internal Slurm launch, as in the qualified
interactive session. The one-task-per-node inventory uses `srun --overlap` too.
Neither enables MPI rank/core sharing. Any rejected binding stops the run.

The default data target is 8 MiB per FFT rank, rounded up to balanced slab
geometry, and 8 MiB per rank per standalone HDF5 checkpoint. These can be raised
with `--fft-mib-per-rank` and `--io-mib-per-rank`. The default loop cap is 512
iterations; achieved times can be shorter than the calibration target at that
cap or the I/O budget cap. The controller shares its remaining logical-write
allowance across remaining I/O conditions and freezes any resulting lower step
count equally for both arms. Default memory use is limited to 25% of observed available/job memory,
including a 256 MiB/rank planning/runtime reserve; peak RSS is checked too.
One checkpoint is retained per active invocation, capped at 8 GiB, with a
1 TiB cumulative logical-write budget including calibration. Increase those
explicit budgets only when the intended filesystem/workload can support them.
The timed I/O includes global flush and close; a final warm restart read checks
correctness outside timing. This does not measure cold reads or certify
physical-media durability.

If the first dense stage passes, increase density on two nodes:

```bash
"$TRIAL_ROOT/runner/trial" production --nodes 2 --ranks-per-node 32,all \
  --pairs 10 --target-seconds 30 --budget-minutes 120 --slurm-overlap
```

Then, if the remaining allocation time and observed memory/I/O costs permit:

```bash
"$TRIAL_ROOT/runner/trial" production --nodes 4,8 --ranks-per-node all \
  --pairs 10 --target-seconds 30 --budget-minutes 120 --slurm-overlap
```

The controller stops at its walltime budget or the Slurm time remaining minus
a two-minute cleanup margin. Unfinished conditions/pairs stay explicitly
partial; a timeout or correctness/placement failure stops further conditions.
It does not resume an old campaign silently. Inspect the saved status before
deciding which new command to run. Logical-write budget exhaustion also retains
partial results; no further I/O is launched.

Use `--groups-per-scale 2` for up to two rotated host groups at each scale, or
`--hosts` for an ordered allocation subset. Host-group results remain separate;
the default uses the first group only. Default FFT geometry scales volume with
rank count; standalone HDF5 holds bytes per rank constant. For a separate
strong-scaling FFT experiment use the same `--shape NX,NY,NZ` at every scale;
both slab distributions must be balanced and fit every selected layout.

The printed `results/production/TIMESTAMP/` contains:

- **`report.html`**: offline quick-look graph and table, with percent change and
  paired 95% bootstrap intervals. Positive means full is slower.
- **`summary.csv` / `summary.json`**: completed-pair means, variation, absolute
  seconds and percent differences. Incomplete pairs are excluded from estimates.
- **`pairs.csv`, `iterations.csv`, `io-modes.csv`**: raw process/loop timing,
  iteration/checkpoint trends, peak RSS and actual HDF5 mode/fallback causes on
  every rank. Mode values are HDF5 enums, not the requested mode alone.
- **`manifest.json`, layouts, inventory and per-launch folders**: private system
  evidence, exact inputs, effective profile/build identities, frozen core maps,
  launch logs, observed affinities and raw caller JSON. Keep these local.
- **`shareable-inventory.json`**: per-node aliases and CPU/core capacity counts,
  without hostnames, CPU IDs, hardware model or private paths.

CSV and HTML omit hostnames and installation paths. Rebuild analysis without
Slurm or rerunning measurements with
`trial production --report /absolute/path/to/results/production/TIMESTAMP`.
Whole-loop walltime is measured directly; process elapsed time also includes
launch, guards, planning and validation. Per-iteration maxima are descriptive,
and must not be summed into a purported observed job critical path. Ten pairs
are a pilot; confirmation still needs a predeclared meaningful threshold,
adequate precision and independent allocations. This mini-application does not
replace a representative CFD/application run.

The [implementation and acceptance plan](14-production-workload-plan.md) records
the broader assessment and later application-confirmation gate.

Choose and retain the scope: **matched caller/stack** or **fixed ordinary caller
with switched complete library stacks**. Earlier stack results keep their scope.
Individual compiler-flag removals and package/component attribution are deferred
until representative job-level costs and their uncertainty have been assessed.

## 4. Test one package when it is ready

For a Mellanox/RDMA system, first qualify the
[UCX build and network selection](00b-openmpi-ucx.md#2-select-the-ucx-transport-prerequisites).
The default TCP/shared-memory build is a bring-up configuration; it does not
qualify the high-speed inter-node experiment. A failed UCX PML/device check
must be resolved before timing rather than skipped.

The driver's primary comparison is complete-stack scope: full package/caller
with full MPI/UCX versus reference package/caller with reference MPI/UCX.
The separate library-only follow-up holds full MPI/UCX fixed. Match network,
placement and workload settings between the two arms in either scope.

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
"$TRIAL_ROOT/runner/trial" test fftw --mpi --nodes 2 --slurm-overlap
```

MPI testing first checks placement/communication using both private stacks, then measures the selected package. It defaults to one rank per selected node; `--ranks-per-node 4` selects four, and actual placement is recorded. `--nodes 1` supports an initial single-node MPI check; it does not establish multi-node behavior. HDF5 MPI uses `test hdf5 --mpi --nodes 2 --slurm-overlap` with `IO_DIR` set to a directory shared by the selected nodes. Omit `--slurm-overlap` for a batch shell with no resource-holding interactive step. Run only one measurement command at a time in the allocation.

## Coming back tomorrow

Set `TRIAL_ROOT` and run `"$TRIAL_ROOT/runner/trial" status`. Completed artifacts are verified. Continue with the next build or test command. After pulling updates, repeat step 1's installer. If the driver reports changed measurement recipes, run `trial refresh-tests`; follow its specific environment/profile instruction for other changes. Refreshing measurements does not rebuild GCC or packages or repeat compiler qualification.

`"$TRIAL_ROOT/runner/trial" logs` lists recent step logs. Inspect a printed path with `less /path/to/log`. A failed child command returns an error to your shell and shows where it stopped. Keep interactive `set -e` off.

## Larger campaigns and recipe references

Once individual pilots work, [08 — separate Slurm jobs](08-slurm-campaign.md) runs the full suite across allocations. [10 — one reserved allocation](10-single-allocation.md) is the optional 8/4/2-node controller. These advanced campaign scripts still require their documented site settings and generation steps; `trial test` is the simpler independent-package route. Do not regenerate/rebuild while queued or running campaigns use the trial tree.

Use a two-node pilot to qualify MPI and the fabric before submitting the larger
campaign with `sbatch`. Slurm grants the resources; the trial's private Open MPI
`mpirun` launches the MPI callers inside that allocation. Interactive
`salloc`/`srun --pty` is useful for diagnosis; qualify overlapping job-step
behavior before nesting `mpirun` under a resource-holding interactive step.

Allocation size and test scales are separate inputs. The current single-job
controller accepts 2, 4 or 8 allocated nodes and scale choices 1, 2, 4 and 8;
it rejects twelve nodes. The individual command's `--nodes N` tests that one
scale on a selected subset, not an automatic sweep. General allocation-driven
planning, including remainder groups, needs an implementation change before
claiming support for arbitrary allocation sizes.

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
