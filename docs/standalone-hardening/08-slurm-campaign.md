# Slurm campaign and performance hypotheses

Use this after the builds, artifact checks, MPI qualification, ReFrame setup and reference callers/guards in 00–06 and [11](11-stack-comparison.md). 07 is needed only for later PIE attribution. The campaign measures the supplied hardening profile's runtime cost and correctness on the recorded workloads. Security properties are checked through build commands and artifacts in 01; a small or undetectable runtime change does not imply that a protection does nothing.

This is the **separate-job campaign**, retained as the fallback and for repeated allocations. [10](10-single-allocation.md) adds the optional single-allocation controller for node subsets and repeated rounds. Both modes use the same paired harness, ReFrame definitions, package binaries and collector.

## 1. Hypotheses and comparisons

These are hypotheses to test on the target system, not predicted benchmark percentages.

| Control or workload | Hypothesis | Measurement and contrast |
|---|---|---|
| Strong stack protector | Added guards may matter most when eligible short functions execute frequently; large arithmetic kernels may dilute the relative cost. | Small FFT/LU, FFT planning, HDF5 small datasets; `full` versus `minus-stack` |
| FORTIFY level 2 | Remaining checks on eligible libc calls may affect call-intensive C paths; optimized-away checks or paths without eligible calls can have little runtime cost. | HDF5 many small datasets and FFT planning; `minus-fortify`; no Fortran FORTIFY claim |
| RELRO and NOW | Relocation protection and eager binding may affect load/startup more than repeated warmed kernels. | Short `*-startup` workloads and `process_elapsed` from every test; `minus-relro` and `minus-now` separately |
| Executable PIE | Code generation/address placement may change caller costs; the effect may depend on the workload. | Three short `*-pie` callers versus `minus-pie`, with the full libraries fixed |
| FFTW/LAPACK size | A size-dependent effect may be visible for small calls and masked by a large kernel or fixed BLAS. | Small and large cases; fixed caller and fixed BLAS; `full` versus `reference` |
| MPI scale | Local overhead may be masked by communication, or influence the critical rank and synchronization; more nodes are not required for overhead to exist. | Fixed global FFT sizes and HDF5 data on 1/2/4/8 nodes; maximum-rank timers, actual placement |
| HDF5 storage | Filesystem variability can mask CPU overhead; many small operations and optional local storage provide complementary views. | Shared-filesystem small/metadata/bulk cases; optional serial local/tmpfs case; same cache/durability conditions in each pair |

Mechanism references: [GCC 12.5 instrumentation](https://gcc.gnu.org/onlinedocs/gcc-12.5.0/gcc/Instrumentation-Options.html), [glibc fortification](https://sourceware.org/glibc/manual/latest/html_node/Source-Fortification.html), [GNU ld](https://sourceware.org/binutils/docs/ld/Options.html). FFTW documents that small MPI problems can be dominated by communication and that performance depends on distribution and problem size ([MPI performance tips](https://www.fftw.org/doc/FFTW-MPI-Performance-Tips.html)). HDF5 documents the costs of many small metadata operations and the importance of layout/access patterns ([metadata I/O](https://support.hdfgroup.org/documentation/hdf5/latest/collective_metadata_io.html)). The expected performance direction above is an experimental inference from those mechanisms.

Start with `TRIAL_SCOPE=stack`, `CAMPAIGN_COMPARATORS=reference` and `RUN_PIE=0` to measure the complete supplied profile on matching callers, packages, BLAS and MPI/UCX. Use [12](12-osu-screen.md) for the small native-metric communication screen. After the initial findings, select `TRIAL_SCOPE=library` and compare independent removals from `full`: `minus-stack`, `minus-fortify`, `minus-relro`, and `minus-now`. LAPACK skips FORTIFY. These are not cumulative removals. MPI/UCX and the benchmark caller stay fixed in library comparisons; the PIE experiment changes only the caller's PIE setting. The primary stack scope already includes matching full/reference MPI/UCX rebuilds; an MPI-only or UCX-only attribution needs a separately defined contrast.

Do not sum removal percentages: controls can interact. The library and caller contrasts establish their recorded scopes; the stack comparison in 11 measures the named trial-owned closure, and an application release outside it needs its own comparison.

## 2. Matrix followed by ReFrame

| Group | ReFrame workloads | Size and scope |
|---|---|---|
| Serial FFTW | `fft-small`, `fft-large`, `fft-3d`, `fft-plan` | 1D 1,024 and 1,048,576 points; 64³; measured planning separate from execution |
| Threaded FFTW | `fft-threads` | 1,048,576 points, four threads on four allocated CPUs |
| Serial HDF5 | `hdf5-small`, `hdf5-metadata`, `hdf5-contiguous`, `hdf5-chunked` | 64 KiB; 1,000 datasets of 128 doubles; 128 MiB contiguous/chunked; uncompressed, buffered writes, warm reads |
| Serial LAPACK | `lapack-small`, `lapack-large` | DGESV at n=128 and n=1,024; matching BLAS in stack scope; fixed full BLAS in library scope; numerical residual checks |
| Startup-sensitive libraries | `fft-startup`, `hdf5-startup`, `lapack-startup` | Short calls; full process time including launch, loading, validation and exit; matching callers in stack scope; fixed hardened caller in library scope |
| Caller PIE | `fft-pie`, `hdf5-pie`, `lapack-pie` | Short calls; full libraries fixed; `minus-pie` only |
| MPI FFTW | `fft-mpi-small`, `fft-mpi`, `fft-mpi-large`, `fft-mpi-plan` | Fixed global 32³, 64³, 128³; measured planning at 64³; maximum-rank timers |
| MPI HDF5 strong scaling | `hdf5-collective`, `hdf5-independent`, `hdf5-mpi-small` | Fixed global 128 MiB bulk and 64 KiB small data, evenly divided among ranks |
| MPI HDF5 weak scaling | Same three HDF5 MPI workloads | 64 MiB bulk and 8 KiB small data per rank; global size grows with rank count |

Initial node counts are **1 and 2**, with **4 and 8** available for focused follow-ups, initially one rank per node. One-node MPI separates MPI/library effects from communication between nodes. An optional four-ranks-per-node lane tests more local concurrency; it is a separately labelled placement, not a continuation of the one-rank lane. The initial maximum is 32 ranks, compatible with the 32³ FFT's slab distribution. Scaling curves across allocations also depend on actual node/fabric conditions; the hardening contrast is paired within each allocation.

The single-node job runs library cases and then PIE cases. Each MPI job runs one node-count/rank-layout/scaling condition sequentially. Its scope selects matching full/reference dependencies or fixed full dependencies explicitly. MPI FFTs always hold global size fixed; the weak-scaling jobs run HDF5 only. Every ReFrame case warms both arms, then alternates full/comparator order over `PAIRS` fresh process pairs. It retains all phases, including reads, planning, and whole-process time, even when the terminal table shows one primary phase.

### Repeatability and a manageable first assessment

Use three levels of repetition and keep their counts separate:

| Level | What repeats | What it establishes |
|---|---|---|
| Kernel iterations | A driver's FFT/LU loop or dataset operations inside one process | Enough timed work to reduce timer noise; one process result, not one statistical sample per iteration |
| Process pairs | A fresh full and reference invocation on the same allocated CPU/rank layout | The paired hardening comparison within that allocation; `PAIRS=20` means 20 observations from 40 timed invocations plus two untimed warmups |
| Allocation repeats | New Slurm jobs, with recorded actual hosts | Sensitivity to time/environment, and to hosts when different nodes are actually assigned; `ALLOCATION_REPEATS` controls this level |

These counts are practical starting budgets, not a guarantee of statistical power:

| Stage | Pairs per case | Allocation repeats | Initial coverage |
|---|---|---|---|
| Qualification/pilot | 10 | 1 | `reference`, serial/threaded and 1/2-node MPI, one rank per node, strong scaling; verify correctness, durations and noise |
| First assessment | 20 | 3 | The same conditions; retain each allocation's estimate, interval and spread separately |
| Focused follow-up | Predetermined from pilot variability and useful precision | At least 3 for the selected condition | Only unresolved or repeatable interesting cases, relevant control removals, or 4/8-node and weak-scaling questions |

For the first assessment, seek **at least two distinct physical hosts of the same CPU/node class** for the serial runs and at least two distinct node sets for each multi-node condition, with jobs at more than one time. Different hosts matter even for a single-core test: frequency, firmware, memory placement, and shared activity can differ. Keep full/reference paired on the same host and allocated CPU within every pair; do not place the two arms on different nodes. Keep the compiler, libraries, inputs, affinity, thread/rank layout, filesystem and cache/durability policy fixed. Record core placement and node inventory. Homogeneous nodes establish this node class's scope; test another architecture as a separate series.

`ALLOCATION_REPEATS=3` submits three separate allocations per condition but does **not** guarantee different hosts. Inspect `allocated-hosts.txt`, the CSV's `node_list`, and Slurm accounting. If all repeats use the same hosts, label them as repetition on those hosts and schedule additional selected runs on different site-approved nodes using the site's allocation controls. Do not claim a check across nodes from job count alone. A simultaneous multi-node FFT/MPI run changes the workload's scale; it does not replace repeating a serial workload on another host.

Use the pilot to choose timed work long enough for stable kernel measurements, increasing repetitions symmetrically and recording changed arguments. Keep startup cases short, because process cost is their subject. For noisy HDF5 shared-storage cases, add the already-supported dedicated local-storage case or repeat at another time; preserve cache/durability labels. Do not drop slow observations merely because they weaken the conclusion. Keep failed/invalid measurements with reasons and rerun the complete affected condition after a documented procedural fault.

Before the first assessment, fix its workload/phase list, pair and allocation counts, and any operational slowdown limit. Complete that planned batch before interpreting it. If precision remains inadequate, define a separate follow-up batch with a fixed larger budget and report both batches; do not keep sampling until an interval happens to cross a desired boundary. More repetitions of one noisy allocation do not replace checks on other hosts. Primary stack `full/reference` comparisons answer the combined trial-scope cost question; removals and secondary phases identify possible causes and stay exploratory.

Report per-allocation paired geometric mean changes and 95% intervals, absolute times, arithmetic mean/sample standard deviation, process-pair count, allocation count and distinct-host count. Show the three allocation estimates as separate points or rows. Do not pool their process pairs, average interval endpoints, or multiply the sample count by kernel iterations or MPI ranks to create a combined interval. A future combined analysis must account for allocation/node grouping. Consistent estimates support a bounded finding; disagreement across allocations calls for investigation. An interval including zero means a zero effect is compatible with these observations, not that overhead is proved absent. No finite sweep proves every scale or application is unaffected.

The distinction between repetitions inside runs and across sessions follows measurement practice in [NIST's defensive-code experiment, section 6.6](https://nvlpubs.nist.gov/nistpubs/TechnicalNotes/NIST.TN.1860.pdf) and [Kalibera and Jones on performance effect-size intervals](https://www.cs.kent.ac.uk/pubs/2012/3233/content.pdf). These sources support preserving levels of variability; they do not prescribe the trial's 10/20-pair or three-allocation budgets.

## 3. Prepare the campaign inputs

Use `/usr/bin/gcc` and `/usr/bin/g++` for the bootstrap if qualified; all payloads still use private GCC 12.5. Before submitting, finish the builds and regenerate the updated HDF5 driver (dataset-count support), MPI placement header/callers, paired harness, and ReFrame definitions. Build reference callers and the rank guard in 11. Build PIE-only callers in 07 only for later attribution. Existing binaries do not gain these features from a documentation update.

For the reference pilot, each package needs `full reference`. For the removal campaign, use `LIB_PROFILES` for FFTW, serial/parallel HDF5 and parallel FFTW, and `LAPACK_PROFILES` for LAPACK in the build loops. If full/reference already exist, select only missing variants; the build guards deliberately reject existing directories. Run artifact and correctness checks for every variant.

Create a site-owned Bash setup file that initializes the module command when needed and loads the **actual required master modules in the site's order**. It must work on batch and compute nodes. It can be empty only when the exported batch environment already supplies the required site setup. The trial environment is activated after this file. An optional MPI tuning file reapplies qualified transport/device settings after activation; do not enable diagnostic UCX logging in timings.

```bash
export TRIAL_ROOT=/absolute/path/to/hardening-trial
export TRIAL_MODULE_SETUP=/absolute/path/to/site-master-setup.sh
export TRIAL_MPI_TUNING=''  # optional absolute Bash file for qualified UCX settings
export SLURM_ACCOUNT=YOUR_ACCOUNT
export SLURM_PARTITION=YOUR_PARTITION
export SLURM_CONSTRAINT=''  # use a homogeneous node class; set the site's constraint if needed
export SHARED_IO_DIR=/absolute/path/to/shared-filesystem/hdf5-hardening-trial
export TRIAL_LOCAL_IO_DIR=''  # optional dedicated node-local/tmpfs directory for serial HDF5
export CAMPAIGN_COMPARATORS=reference TRIAL_SCOPE=stack RUN_PIE=0
# After building selected removals, change scope to library:
# export TRIAL_SCOPE=library
# export CAMPAIGN_COMPARATORS=reference,minus-stack,minus-fortify,minus-relro,minus-now
export NODE_COUNTS='1 2'  # expand deliberately after the screen
export RANK_LAYOUTS='1'  # optional separate lane: '1 4'
export RUN_WEAK=0 PAIRS=10 TRIAL_WALLTIME=02:00:00 TRIAL_EXCLUSIVE=1
export ALLOCATION_REPEATS=1  # qualification; use 3 for the first assessment
export TRIAL_REGRESSION_LIMIT_PERCENT=''  # agree a workload limit before results, or leave descriptive
test -f "$TRIAL_MODULE_SETUP"
mkdir -p "$SHARED_IO_DIR" "$TRIAL_ROOT/reframe"
```

The optional local directory must be dedicated to the trial and have room for the buffers/files. No cache-drop operation is used. `TRIAL_EXCLUSIVE=1` requests exclusive nodes; use the site's permitted resource policy and adjust walltime from the pilot. Jobs bill the supplied account. This procedure uses the existing Slurm and never builds or updates it.

## 4. Create the node inventory and batch driver

These files are generated under the trial root. Slurm allocates the jobs; ReFrame uses its local scheduler inside each allocation so both arms share resources. `srun` below is only for node inventory. The timed MPI caller is launched by the private `mpirun` in `paired.py`.

```bash
cat > "$TRIAL_ROOT/reframe/inspect-node.sh" <<'SH'
#!/bin/bash
set -euo pipefail
source "$TRIAL_MODULE_SETUP"
source "$TRIAL_ROOT/env.sh"
if [[ "$1" == mpi-* ]]; then
    source "$TRIAL_ROOT/mpi-env.sh"
    if test -n "${TRIAL_MPI_TUNING:-}"; then source "$TRIAL_MPI_TUNING"; fi
fi
dest="$2/node-$(hostname)"
mkdir -p "$dest"
uname -a > "$dest/host.txt"
lscpu > "$dest/cpu.txt"
taskset -pc $$ > "$dest/affinity.txt"
"$CC" --version > "$dest/compiler.txt"
df -T "$SHARED_IO_DIR" > "$dest/filesystem.txt"
if type module >/dev/null 2>&1; then module list > "$dest/modules.txt" 2>&1; fi
printf '%s\n' "PATH=$PATH" "LD_LIBRARY_PATH=$LD_LIBRARY_PATH" \
  "UCX_TLS=${UCX_TLS-}" "UCX_NET_DEVICES=${UCX_NET_DEVICES-}" \
  > "$dest/paths-and-transport.txt"
if [[ "$1" == mpi-* ]]; then
    "$UCX_PREFIX/bin/ucx_info" -d > "$dest/ucx-devices.txt"
    ldd "$MPI_PREFIX/lib/openmpi/mca_pml_ucx.so" > "$dest/ucx-component.txt"
    ulimit -l > "$dest/memlock.txt"
fi
SH
cat > "$TRIAL_ROOT/reframe/campaign-job.sh" <<'SH'
#!/bin/bash
set -euo pipefail
phase=${1:?serial or mpi-strong or mpi-weak}
export TRIAL_EXPECTED_NODES=${2:?node count} RANKS_PER_NODE=${3:?ranks per node}
source "$TRIAL_MODULE_SETUP"
source "$TRIAL_ROOT/env.sh"
export REFRAME="$TRIAL_ROOT/tools/reframe-venv/bin/reframe"
export TRIAL_REPLICATE_ID=${TRIAL_REPLICATE_ID:-1}
export TRIAL_ALLOCATION_MODE=separate-jobs TRIAL_REPEAT_SCOPE=allocation
unset TRIAL_SELECTED_HOSTS
export TRIAL_RUN_LABEL="$phase-n${TRIAL_EXPECTED_NODES}-rpn${RANKS_PER_NODE}-rep${TRIAL_REPLICATE_ID}"
dest="$TRIAL_ROOT/results/campaigns/$CAMPAIGN_ID/$TRIAL_RUN_LABEL-$SLURM_JOB_ID"
mkdir -p "$dest"
test "${SLURM_JOB_NUM_NODES:?}" -eq "$TRIAL_EXPECTED_NODES"
scontrol show job "$SLURM_JOB_ID" > "$dest/slurm-job.txt"
scontrol show hostnames "$SLURM_JOB_NODELIST" > "$dest/allocated-hosts.txt"
if [[ "$phase" == mpi-* ]]; then
    source "$TRIAL_ROOT/mpi-env.sh"
    if test -n "${TRIAL_MPI_TUNING:-}"; then source "$TRIAL_MPI_TUNING"; fi
    unset UCX_LOG_LEVEL
    export MPI_NP=$((TRIAL_EXPECTED_NODES*RANKS_PER_NODE))
    export MPI_MAP="ppr:$RANKS_PER_NODE:node"
    export HDF5_SCALING_MODE=${phase#mpi-}
else
    export MPI_NP=0 FFT_THREADS=4
    cpus=$(python3 - <<'PY'
import os
cpus=sorted(os.sched_getaffinity(0))
if len(cpus)<4: raise SystemExit('Need four allocated CPUs for fft-threads')
print(','.join(map(str,cpus[:4])))
PY
)
    export THREAD_CPUSET="$cpus" CPUSET="${cpus%%,*}"
fi
"$SLURM_BINDIR/srun" --nodes="$TRIAL_EXPECTED_NODES" \
  --ntasks="$TRIAL_EXPECTED_NODES" --ntasks-per-node=1 --cpus-per-task=1 \
  /bin/bash "$TRIAL_ROOT/reframe/inspect-node.sh" "$phase" "$dest"
run_group() {
    local group=$1 workloads=$2 comparators=$3 io=$4
    export WORKLOADS="$workloads" COMPARATORS="$comparators" IO_DIR="$io"
    export RUN_ID="$CAMPAIGN_ID-$TRIAL_RUN_LABEL-$SLURM_JOB_ID-$group"
    mkdir -p "$IO_DIR" "$TRIAL_ROOT/results/reframe/$RUN_ID"
    df -T "$IO_DIR" > "$dest/$group-filesystem.txt"
    printf '%s\n' "$RUN_ID" >> "$dest/sessions.txt"
    "$REFRAME" -C "$TRIAL_ROOT/reframe/settings.py" -c "$TRIAL_ROOT/reframe/hardening.py" \
      -r --exec-policy=serial --performance-report \
      --prefix="$TRIAL_ROOT/results/reframe/$RUN_ID/rfm" \
      --report-file="$TRIAL_ROOT/results/reframe/$RUN_ID/report.json" \
      2>&1 | tee "$TRIAL_ROOT/results/reframe/$RUN_ID/console.log"
}
# Campaign PASS checks correctness/procedure; CSV classifies the agreed limit.
unset MAX_SLOWDOWN_PERCENT
case "$phase" in
    serial)
        run_group libraries \
          fft-small,fft-large,fft-3d,fft-plan,fft-threads,hdf5-small,hdf5-metadata,hdf5-contiguous,hdf5-chunked,lapack-small,lapack-large,fft-startup,hdf5-startup,lapack-startup \
          "$CAMPAIGN_COMPARATORS" "$SHARED_IO_DIR"
        if test "${RUN_PIE:-0}" = 1; then run_group pie fft-pie,hdf5-pie,lapack-pie minus-pie "$SHARED_IO_DIR"; fi
        if test -n "${TRIAL_LOCAL_IO_DIR:-}"; then
            run_group local-io hdf5-small,hdf5-metadata,hdf5-contiguous,hdf5-chunked \
              "$CAMPAIGN_COMPARATORS" "$TRIAL_LOCAL_IO_DIR"
        fi ;;
    mpi-strong)
        run_group strong fft-mpi-small,fft-mpi,fft-mpi-large,fft-mpi-plan,hdf5-collective,hdf5-independent,hdf5-mpi-small \
          "$CAMPAIGN_COMPARATORS" "$SHARED_IO_DIR" ;;
    mpi-weak)
        run_group weak hdf5-collective,hdf5-independent,hdf5-mpi-small \
          "$CAMPAIGN_COMPARATORS" "$SHARED_IO_DIR" ;;
    *) exit 2 ;;
esac
SH
chmod +x "$TRIAL_ROOT/reframe/inspect-node.sh" "$TRIAL_ROOT/reframe/campaign-job.sh"
```

MPI callers record rank hostnames and abort if actual node counts or ranks per node differ from the declared layout. Their placement check is outside kernel timers; whole-process time includes it. Confirm the selected UCX transport on the actual compute nodes. `ldd` at the controller cannot establish remote-node linkage by itself.

## 5. Submit the sequence

The submitter checks installed variants before allocating resources. Jobs use `afterok` dependencies so a failed job prevents subsequent conditions from running on an invalid setup. ReFrame also runs cases sequentially inside each job. Node counts, rank layouts, partition/constraint and resource options are explicit; `#SBATCH` directives cannot expand shell variables. [Slurm sbatch documentation](https://slurm.schedmd.com/sbatch.html)

```bash
cat > "$TRIAL_ROOT/reframe/submit-campaign.sh" <<'SH'
#!/bin/bash
set -euo pipefail
: "${SLURM_ACCOUNT:?}" "${SLURM_PARTITION:?}" "${TRIAL_MODULE_SETUP:?}" "${SHARED_IO_DIR:?}"
export ALLOCATION_REPEATS=${ALLOCATION_REPEATS:-1}
test -f "$TRIAL_MODULE_SETUP"
if test -n "${TRIAL_MPI_TUNING:-}"; then test -f "$TRIAL_MPI_TUNING"; fi
source "$TRIAL_MODULE_SETUP"
source "$TRIAL_ROOT/env.sh"
test "${HARDENING_SET:-listed}" = listed
export TRIAL_SCOPE=${TRIAL_SCOPE:-stack} RUN_PIE=${RUN_PIE:-0}
case "$TRIAL_SCOPE" in stack|library) ;; *) exit 2 ;; esac
case "$RUN_PIE" in 0|1) ;; *) exit 2 ;; esac
test -x "$TRIAL_ROOT/tools/reframe-venv/bin/reframe"
test -f "$TRIAL_ROOT/reframe/campaign-job.sh"
read -r -a comparators <<< "${CAMPAIGN_COMPARATORS//,/ }"
test "${#comparators[@]}" -gt 0
for p in "${comparators[@]}"; do
    case "$p" in reference|minus-stack|minus-fortify|minus-relro|minus-now) ;; *) exit 2 ;; esac
done
for package in fftw hdf5 lapack fftw-mpi hdf5-mpi; do
    test -x "$TRIAL_ROOT/bench/$package-fixed"
    for p in full "${comparators[@]}"; do
        if [[ "$package:$p" == lapack:minus-fortify ]]; then continue; fi
        test -d "$TRIAL_ROOT/install/$package/$p/lib"
    done
done
if test "${RUN_PIE:-0}" = 1; then
    test "${TRIAL_SCOPE:-stack}" = library
    for package in fftw hdf5 lapack; do test -x "$TRIAL_ROOT/bench/$package-minus-pie"; done
fi
if test "${TRIAL_SCOPE:-stack}" = stack; then
    test "$CAMPAIGN_COMPARATORS" = reference
    for package in fftw hdf5 lapack fftw-mpi hdf5-mpi; do
        test -x "$TRIAL_ROOT/bench/$package-reference"
    done
    test -f "$TRIAL_ROOT/mpi-env-reference.sh"
    test -x "$TRIAL_ROOT/bench/rank-exec.sh"
    for p in full reference; do test -f "$TRIAL_ROOT/install/blas/$p/lib/libblas.so"; done
fi
test -f "$TRIAL_ROOT/mpi-env.sh"
read -r -a nodes_list <<< "$NODE_COUNTS"
read -r -a layouts <<< "$RANK_LAYOUTS"
test "${#nodes_list[@]}" -gt 0
test "${#layouts[@]}" -gt 0
for n in "${nodes_list[@]}"; do case "$n" in 1|2|4|8) ;; *) exit 2 ;; esac; done
for r in "${layouts[@]}"; do case "$r" in 1|4) ;; *) exit 2 ;; esac; done
python3 - <<'PY'
import math, os, re
if int(os.environ['PAIRS'])<2: raise SystemExit('PAIRS must be at least two')
if not re.fullmatch(r'[1-9][0-9]*',os.environ['ALLOCATION_REPEATS']):
    raise SystemExit('ALLOCATION_REPEATS must be a positive decimal integer without leading zeros')
limit=os.environ.get('TRIAL_REGRESSION_LIMIT_PERCENT','')
if limit and (not math.isfinite(float(limit)) or float(limit)<0):
    raise SystemExit('The agreed regression limit must be finite and nonnegative')
PY
export CAMPAIGN_ID
CAMPAIGN_ID="$(date -u +%Y%m%dT%H%M%SZ)-$$"
dir="$TRIAL_ROOT/results/campaigns/$CAMPAIGN_ID"
mkdir -p "$dir"
python3 - "$dir/inputs.json" <<'PY'
import json, os, pathlib, sys
names=('CAMPAIGN_ID','CAMPAIGN_COMPARATORS','TRIAL_SCOPE','RUN_PIE','TRIAL_PROCEDURE_COMMIT','NODE_COUNTS','RANK_LAYOUTS','RUN_WEAK',
       'PAIRS','ALLOCATION_REPEATS','TRIAL_WALLTIME','TRIAL_EXCLUSIVE','TRIAL_REGRESSION_LIMIT_PERCENT',
       'SLURM_ACCOUNT','SLURM_PARTITION','SLURM_CONSTRAINT','SHARED_IO_DIR',
       'TRIAL_LOCAL_IO_DIR','TRIAL_MODULE_SETUP','TRIAL_MPI_TUNING',
       'MPI_GLOBAL_ELEMENTS','MPI_GLOBAL_SMALL_ELEMENTS',
       'MPI_ELEMENTS_PER_RANK','MPI_SMALL_ELEMENTS_PER_RANK')
pathlib.Path(sys.argv[1]).write_text(json.dumps({n:os.environ.get(n,'') for n in names},indent=2)+'\n')
PY
printf 'job_id\tphase\tnodes\tranks_per_node\treplicate\n' > "$dir/jobs.tsv"
common=(--parsable --account="$SLURM_ACCOUNT" --partition="$SLURM_PARTITION"
        --time="$TRIAL_WALLTIME" --export=ALL --chdir="$TRIAL_ROOT")
if test -n "${SLURM_CONSTRAINT:-}"; then common+=(--constraint="$SLURM_CONSTRAINT"); fi
if test "${TRIAL_EXCLUSIVE:-1}" = 1; then common+=(--exclusive); fi
dependency=()
submit() {
    local phase=$1 nodes=$2 rpn=$3 cpus=$4 response id
    response=$("$SLURM_BINDIR/sbatch" "${common[@]}" ${dependency[@]+"${dependency[@]}"} \
      --job-name="hardening-$phase-${nodes}n-${rpn}rpn-rep$TRIAL_REPLICATE_ID" \
      --nodes="$nodes" --ntasks="$((nodes*rpn))" --ntasks-per-node="$rpn" \
      --cpus-per-task="$cpus" --output="$dir/%j.out" --error="$dir/%j.err" \
      "$TRIAL_ROOT/reframe/campaign-job.sh" "$phase" "$nodes" "$rpn")
    id=${response%%;*}
    [[ "$id" =~ ^[0-9]+$ ]]
    printf '%s\t%s\t%s\t%s\t%s\n' "$id" "$phase" "$nodes" "$rpn" "$TRIAL_REPLICATE_ID" >> "$dir/jobs.tsv"
    dependency=(--dependency="afterok:$id" --kill-on-invalid-dep=yes)
}
for ((repeat=1; repeat<=ALLOCATION_REPEATS; repeat++)); do
    export TRIAL_REPLICATE_ID=$repeat
    submit serial 1 1 4
    for rpn in "${layouts[@]}"; do
        for nodes in "${nodes_list[@]}"; do
            submit mpi-strong "$nodes" "$rpn" 1
            if test "${RUN_WEAK:-1}" = 1; then submit mpi-weak "$nodes" "$rpn" 1; fi
        done
    done
done
printf 'Campaign: %s\nManifest: %s/jobs.tsv\n' "$CAMPAIGN_ID" "$dir"
SH
chmod +x "$TRIAL_ROOT/reframe/submit-campaign.sh"
/bin/bash "$TRIAL_ROOT/reframe/submit-campaign.sh"
```

For qualification, set `NODE_COUNTS='1 2'`, `RUN_WEAK=0`, `CAMPAIGN_COMPARATORS=reference`, `PAIRS=10`, and `ALLOCATION_REPEATS=1`: this submits three jobs. After inspecting that pilot, the following settings submit nine jobs for the first assessment, with 20 pairs per case and three allocation repeats. An assessment job includes serial/threaded/startup groups; PIE-only attribution runs only with library scope and `RUN_PIE=1`; repeat selected narrower cases through 06 when investigating a particular observation.

```bash
export NODE_COUNTS='1 2' RANK_LAYOUTS='1' RUN_WEAK=0
export CAMPAIGN_COMPARATORS=reference PAIRS=20 ALLOCATION_REPEATS=3
/bin/bash "$TRIAL_ROOT/reframe/submit-campaign.sh"
```

Expand to 4/8 nodes, weak scaling, or control removals when those answer a remaining question. Repeating the default full nine-job scale sweep three times submits 27 jobs, so set the coverage deliberately before submission. Submitting is asynchronous; it is not evidence that jobs completed. Use the printed campaign ID for collection. Keep the trial tree fixed while jobs are queued/running; do not rebuild callers/libraries or edit generated configurations mid-campaign. Retain the procedure commit SHA with `inputs.json`. Cancel an unwanted queued campaign with the site's normal `scancel` procedure using its manifest's job IDs.

## 6. Collect and interpret every phase

Each session preserves ReFrame `report.json`/console output, loaded-library records, driver/placement logs, raw paired CSV, and per-phase summary JSON. Node inventory and Slurm resource details are under `results/campaigns/CAMPAIGN_ID/`. This collector makes one CSV row per completed workload/comparator/phase without mixing campaign IDs or averaging different scales.

```bash
cat > "$TRIAL_ROOT/reframe/collect-campaign.py" <<'PY'
import csv, json, math, os, pathlib, sys
root=pathlib.Path(os.environ['TRIAL_ROOT'])
campaign=sys.argv[1]
dest=root/'results'/'campaigns'/campaign
if not dest.is_dir(): raise SystemExit('Unknown campaign')
fields=['session','run_label','job_id','replicate','repeat_scope','allocation_mode',
        'node_list','allocated_node_list','allocation_nodes','step_id','nodes','ranks_per_node','ranks','scaling','io_dir',
        'package','workload','comparator','scope','effective_profile_ids','phase','primary','pairs',
        'full_seconds','comparator_seconds','runtime_increase_percent','ci_low','ci_high',
        'full_seconds_mean','full_seconds_stdev','comparator_seconds_mean','comparator_seconds_stdev',
        'paired_change_stdev_percent_points','limit_percent','interpretation','summary_path']
rows=[]
for path in sorted((root/'results'/'reframe').glob('*/paired/*/*/*/summary.json')):
    result=json.loads(path.read_text()); context=result.get('context',{})
    if context.get('CAMPAIGN_ID')!=campaign: continue
    for phase,value in result['phases'].items():
        low,high=value['bootstrap_95_percent_interval']
        primary=phase==result.get('primary_phase')
        limit=context.get('TRIAL_REGRESSION_LIMIT_PERCENT','')
        interpretation='descriptive'
        if primary and result['comparator']=='reference' and limit:
            threshold=float(limit)
            if not math.isfinite(threshold) or threshold<0: raise SystemExit('Invalid agreed limit')
            interpretation=('below_limit' if high<=threshold else
                            'regression_above_limit' if low>threshold else 'inconclusive')
        rows.append(dict(zip(fields,[context.get('RUN_ID'),context.get('TRIAL_RUN_LABEL'),context.get('SLURM_JOB_ID'),
            context.get('TRIAL_REPLICATE_ID'),context.get('TRIAL_REPEAT_SCOPE'),context.get('TRIAL_ALLOCATION_MODE'),
            context.get('TRIAL_SELECTED_HOSTS') or context.get('SLURM_JOB_NODELIST'),
            context.get('SLURM_JOB_NODELIST'),context.get('SLURM_JOB_NUM_NODES'),context.get('SLURM_STEP_ID'),
            context.get('TRIAL_EXPECTED_NODES'),context.get('RANKS_PER_NODE'),context.get('MPI_NP'),
            context.get('SCALING_MODE'),context.get('IO_DIR'),result['package'],result['case'],
            result['comparator'],result['scope'],';'.join(result.get('effective_profile_ids',[])) or 'manual-unrecorded',phase,primary,value['pairs'],
            value['full_runtime_seconds_geomean'],value['comparator_runtime_seconds_geomean'],
            value['full_runtime_increase_percent'],low,high,
            value['full_runtime_seconds_mean'],value['full_runtime_seconds_stdev'],
            value['comparator_runtime_seconds_mean'],value['comparator_runtime_seconds_stdev'],
            value['paired_runtime_increase_stdev_percent_points'],limit,interpretation,str(path)])))
if not rows: raise SystemExit('No completed paired results for this campaign')
with (dest/'phases.csv').open('w',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=fields); writer.writeheader(); writer.writerows(rows)
print(f'{len(rows)} completed phase rows: {dest / "phases.csv"}')
print('Check Slurm states and all ReFrame reports before declaring the campaign complete.')
PY
# Set this to the ID printed by the submitter.
export CAMPAIGN_ID=REPLACE_WITH_PRINTED_ID
job_ids=$(awk 'NR>1 {print $1}' "$TRIAL_ROOT/results/campaigns/$CAMPAIGN_ID/jobs.tsv" | paste -sd, -)
"$SLURM_BINDIR/sacct" -j "$job_ids" --format=JobID,State,ExitCode,Elapsed,AllocCPUS,NodeList \
  > "$TRIAL_ROOT/results/campaigns/$CAMPAIGN_ID/slurm-accounting.txt"
python3 "$TRIAL_ROOT/reframe/collect-campaign.py" "$CAMPAIGN_ID"
```

The CSV distinguishes the declared primary phase from exploratory phases. Positive runtime increase means full was slower. With a predeclared limit, an upper interval below the limit supports the recorded workload meeting it; a lower interval above the limit supports a regression exceeding it; an interval crossing the limit is inconclusive. Removal and PIE comparisons remain descriptive attribution experiments. If a workload-specific limit is required, agree and record a separate campaign/analysis rule for that workload rather than adopting an arbitrary universal percentage.

ReFrame PASS in this campaign means correctness and the measurement procedure succeeded. It does not mean overhead is acceptable. Inspect skipped/failed tests and Slurm completion/exit codes before saying the planned matrix ran. A failed job can leave dependent jobs cancelled or pending. The collector includes only completed summaries; missing rows are not zero overhead. Retain the procedure commit SHA, sources/build logs, and the campaign's input settings with the results.
