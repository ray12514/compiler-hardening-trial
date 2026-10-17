# 12 - Automated OSU fixed-caller MPI/UCX comparison

Run the next [fixed-caller FFTW/HDF5 workflow](README.md#next-session-fixed-caller-application-pattern-assessment)
first, then OSU. This adapter compares the existing **reference Open MPI + UCX**
with **hardened Open MPI + UCX**, using the exact same ordinarily compiled OSU
executable for both arms. It measures their combined runtime effect; it does
not isolate MPI from UCX, compare different MPI implementations, or apply full
hardening to the OSU caller. No MVAPICH installation is required.

The earlier manual matched-caller screen is retained in Git history. Its `stack`
results retain that scope; do not pool them with these `fixed-caller-mpi-ucx`
results. Use the automated route below for the new assessment.

## 1. Stage everything on the connected login node

After pulling and reinstalling the driver, use:

```bash
export TRIAL_ROOT="$HOME/COMPILER_HARDENING"
"$TRIAL_ROOT/runner/trial" osu prepare
"$TRIAL_ROOT/runner/trial" osu prepare --check
"$TRIAL_ROOT/runner/trial" prepare-tests --check
```

`osu prepare` downloads only the pinned CPU benchmark source archive to
`downloads/`. It does not build or run MPI. The stable release is OSU 7.5.2,
from the [official release page](https://mvapich.cse.ohio-state.edu/benchmarks/):

- Archive: `osu-micro-benchmarks-7.5.2.tar.gz`
- URL: `https://mvapich.cse.ohio-state.edu/download/mvapich/osu-micro-benchmarks-7.5.2.tar.gz`
- SHA-256: `618de3d0b1122f73a9229177d2da1e5cd62e431190580cb915f2605849cbbbdc`

If the login node cannot download directly, transfer that archive from a
connected staging host, then import it with the same checksum check:

```bash
"$TRIAL_ROOT/runner/trial" osu prepare --from-dir /absolute/path/to/transferred-archives
```

ReFrame must already be prepared through the existing `prepare-tests` workflow;
use its offline wheelhouse route if needed. MPI/UCX and the compiler are the
completed trial installations. The release archive includes `configure` and
Makefiles, so no autoreconf, PAPI, GPU toolkit or extra Python dependency is
needed. OSU 7.5.2 has a configure quirk: passing `--disable-papi` enables PAPI;
the adapter omits that option and retains its verified disabled default.
The network-disabled build and test commands never download missing inputs.

## 2. Build once, on the login or compute node

The source archive must be staged first. Build where the private reference
MPI/compiler toolchain is available and usable:

```bash
"$TRIAL_ROOT/runner/trial" osu build --jobs 4
"$TRIAL_ROOT/runner/trial" osu build --check
```

These commands work without network access and do not launch MPI benchmarks.
When using `-march=native`, build on a representative compute node if the login
CPU differs. Match `--jobs` to the CPUs available for the build; the default is
one. A single-node build allocation is sufficient. Compilation is outside the
measured sample series.

The adapter builds only `osu_latency`, `osu_bw`, `osu_allreduce` and `osu_alltoall`
with the reference executable flags and reference MPI wrappers. It retains
configuration/verbose build logs, ELF observations, the pinned source-tree
fingerprint, flags, MPI/UCX dependency identities and binary SHA-256 values.
Callers live under `install/osu/fixed/IDENTITY/bin/`; logs and source/build files
live under `build/osu/IDENTITY/`. `runner/osu-build.json` identifies the active
build. Existing packages, pilot callers and results are preserved.

An unchanged completed build is verified and reused. If an OSU build fails,
inspect its saved configure/build logs, then use `osu build --retry` after
resolving the cause. A modified source tree or installed executable is rejected;
it cannot silently retain the pinned release identity.

## 3. Finish the next workflow, then run OSU

Use the result directory printed by the next **completed deployment-scope**
production run, not its ReFrame wrapper directory. If ReFrame was used, its
`campaign.json` points to that production directory. The OSU test checks
`status=finished`, `scope=deployment` and matching full/reference MPI/UCX build
records before launching anything. A short completed next-phase pilot meets
this ordering gate; completion of every future scale is not required.

Inside the next existing allocation with at least two nodes:

```bash
export PRODUCTION_RESULT=/absolute/path/to/results/production/COMPLETED_RUN
"$TRIAL_ROOT/runner/trial" osu test --after-production "$PRODUCTION_RESULT" \
  --reframe --nodes 2 --ranks-per-node 16 \
  --pairs 4 --iterations 1000 --warmups 100 \
  --budget-minutes 60 --slurm-overlap
```

Keep `--slurm-overlap` in the interactive session that required it. It reaches
Open MPI's internal Slurm launcher and the inventory `srun`; it does not enable
MPI oversubscription. Saved UCX RC/shared-memory settings, private launchers,
per-host WEKA exclusions and one rank per selected physical core are reused.
Every rank verifies the unchanged benchmark hash, selected MPI/UCX library
paths, binding and RC device availability before OSU qualification. Both arms
run OSU data validation separately before measured process pairs. Verbose UCX
logging and validation are off during the measured series.

| Benchmark | Default bytes | Placement | Native metric |
|---|---|---|---|
| `osu_latency` | 1, 1024, 65536 | Exactly 2 ranks, one on each of the first 2 selected nodes | us, lower is better |
| `osu_bw` | 1024, 65536, 1048576 | Exactly 2 ranks, one per node | MB/s, higher is better |
| `osu_allreduce` | 16, 1024, 65536 | Requested collective node scales and rank density | us, lower is better |
| `osu_alltoall` | 16, 1024, 4096 | Same collective layouts | us, lower is better |

The two-rank tests remain two-rank tests even when dense collectives are selected.
Point-to-point datatype is MPI_CHAR; allreduce is MPI_INT and alltoall MPI_CHAR.
The bandwidth window is the pinned release default of 64. Buffer estimates
include communicator-size growth and a 256 MiB/rank runtime reserve, checked
against the granted/available memory budget. Four pairs establish a runnable
pilot, not acceptable overhead.

After reviewing noise and cost, use an even pair count such as `--pairs 20` and
repeat selected conditions in independent allocations. Use
`--ranks-per-node all` for all audited eligible physical cores in collectives;
`--nodes 2,4,8` requests scales within the existing allocation, not new nodes.
Run larger scales separately if needed to preserve the run budget.
`--hosts` selects an ordered allocation subset. Optional `--benchmarks` and
`--messages` choose a predeclared subset; retain all selected outcomes. Message
overrides are limited to 1 MiB and allreduce sizes must be multiples of four.

The controller bounds walltime by `--budget-minutes`, each launch by `--timeout`,
and the scheduler time remaining minus a cleanup margin. Balanced randomized
AB/BA process-pair order uses identical OSU arguments across arms. OSU internal
iterations and ranks are not independent samples. Budget exhaustion retains
partial data; invalid output, validation, placement or dependency failures stop
the run. No incomplete pair enters an estimate.

## 4. Read and export results

The driver prints `results/osu/TIMESTAMP/` with:

- `summary.csv`, `summary.json`, `report.html`: per-case native means/spread,
  paired deterioration estimates and 95% bootstrap intervals, with pair counts
  and partial status. The offline HTML includes a plot.
- `pairs.csv`: native observations and whole-launch elapsed seconds for each
  arm/process pair. Whole-launch seconds are not substituted for OSU latency.
- `manifest.json`, inventories, layouts and per-launch logs/rank JSON: private
  build, allocation, caller-hash, loaded-library and qualification evidence.

With `--reframe`, `results/osu-reframe/TIMESTAMP/report.json` contains ReFrame
performance values in us or MB/s, plus deterioration percentages/intervals and
pair counts. `campaign.json` links to the underlying OSU directory. A partial
campaign does not pass ReFrame completion sanity. Keep ReFrame job reports and
rank inventories private; the controller's metric-only CSV/HTML omit hostnames
and installation paths.

Regenerate exports later without Slurm, a build or another benchmark run:

```bash
"$TRIAL_ROOT/runner/trial" osu report /absolute/path/to/results/osu/RUN
```

Latency deterioration is `100 * (mean full / mean reference - 1)`. Bandwidth
loss is `100 * (1 - mean full / mean reference)`. Positive means deterioration
in either case; they are separate metrics, not interchangeable runtime costs.
Intervals resample complete fresh-process pairs, retaining arm pairing. Passing
execution does not establish zero overhead, security efficacy or policy
acceptance. This OSU lane supplements FFTW/HDF5 application-pattern evidence;
it does not replace it or identify which individual flag caused a difference.
