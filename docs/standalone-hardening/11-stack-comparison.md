# 11 — Complete profile first, then attribution

**Normal route:** follow the [README](README.md), then run `"$TRIAL_ROOT/runner/trial" build all`. The driver runs the applicable blocks below in child shells, including prerequisites. These numbered sections are recipe references; do not paste all of them after using the driver.

This is the primary experiment agreed for the standalone trial: build and qualify the complete supplied profile first, compare it with a matched reference, and investigate selected controls only afterward. ReFrame runs prebuilt artifacts inside operator-controlled Slurm allocations; this campaign is outside CI.

The next assessment after the package pilot is the
[production-density and sustained-workload plan](14-production-workload-plan.md):
allocated-core MPI layouts, repeated FFT work and distributed checkpoint I/O,
then a measured job-level comparison. The primary scope remains full versus
reference throughout. Package/component and individual-flag attribution are
later investigations; they are not prerequisites or extra axes of this campaign.

## 1. Build scope and sequence

The primary scope contains the **trial-owned** FFTW, serial/parallel HDF5, LAPACK plus its reference-implementation BLAS, Open MPI/its bundled dependencies, UCX, and benchmark callers. GCC 12.5, binutils, CMake, Python/ReFrame, the OS, Slurm, fabric drivers and approved site libraries stay fixed. This is not a rebuild of every library on the machine. Record those fixed dependencies as part of the experiment's boundary. From the documentation checkout, set `export TRIAL_PROCEDURE_COMMIT=$(git rev-parse HEAD)` before the campaign; retain source checksums and actual compile/link commands with it.

| Stage | Builds and comparison | Question |
|---|---|---|
| Qualification | Full flags on each applicable language/output; upstream tests, artifact inspection and two-node transport checks | Did the proposed configuration build and work? |
| Primary screen | Matching full/reference callers, packages, BLAS and MPI/UCX; initial serial/threaded and 1/2-node cases | What is the combined performance effect of the supplied profile in this trial scope? |
| Production assessment | Matching full/reference stacks at allocated-core density, sustained compute/communication and checkpoint cadence; selected 2/4/8-node groups | What is the elapsed-time, throughput and resource cost for representative repeated job work? |
| Package attribution | One full caller and full dependency stack; switch only the package library | Which package rebuild helps explain an observed change? |
| Control attribution | Full versus one independently removed control for a selected package/workload | What changes when this control is absent, with the other controls retained? |
| Extended attribution | Selected MPI/UCX component rebuilds after the production assessment | Which dependency rebuild helps explain a reproducible combined effect? |

The reference explicitly disables the variable controls; optimization, CPU target, PIC for shared libraries, warnings and non-executable stack stay fixed. `full` denotes all applicable controls in the recorded supplied list, not every GCC option or an independent certification of STIG compliance. The per-control hypotheses are in [08](08-slurm-campaign.md#1-hypotheses-and-comparisons). Write hypotheses before running; do not add removal percentages together.

**Manual reference order (the driver handles these dependencies):** 00 (reuse the GCC you finished) -> 01 (profiles/qualification/harness) -> 00b (full then reference UCX/Open MPI) -> 02/03/04 (packages and matching BLAS) -> 05 (matching parallel packages) -> 06 (ReFrame) -> this section's reference callers and guards -> 08 or 10. [12](12-osu-screen.md) adds a small OSU screen without a Cartesian product of MPI/package/flag variants. Do not build removal variants yet.

### If you are partway through a build

Pull the documentation into its separate checkout. A qualified, unchanged full GCC/MPI/package installation can be retained. Select only missing profiles in `MPI_VARIANTS`, `BLAS_VARIANTS` and the package arrays; the build guards intentionally reject existing directories. A partially configured directory is not a qualified installation. Preserve it and its logs, then choose a fresh build directory/prefix for a corrected configuration. Do not delete source/results or overwrite installed libraries while jobs are queued or running.

The older `blas-fixed` reference-only installation does not supply the full/reference numerical-stack experiment. Build `install/blas/full` and `install/blas/reference` using 04; verify which BLAS the existing LAPACK/caller actually loads before reuse. Rebuild a caller when its source, compile flags or intended dependency interface changes. Regenerate `profiles.sh`, `paired.py`, ReFrame definitions and campaign scripts from the updated procedures; pulling Markdown does not update generated files automatically.

### Compatibility decisions during the build

For the automated route, `trial setup` records supported controls and any explicit compiler rejection before expensive builds. Its reduced identity and exact vectors are carried into summaries and campaign CSV. Package build/correctness errors stop with logs; `build --retry` preserves the failed attempt and starts fresh after the cause is resolved. It does not guess that an arbitrary package failure is caused by hardening.

For the manual route, use the qualification and `logs/compatibility.tsv` procedure in [01](01-common.md#2-qualify-flags-before-expensive-builds). Preserve the exact error and actual compiler/linker commands. A flag accepted but overridden by the build system requires a build fix. A required control rejected by the package requires a resolved configuration or an explicitly named, approved reduced profile and a new affected build; do not silently omit it. Update the procedure and build manifest before timing. Existing results retain their original identity.

Hardening GCC's own executables is a separate experiment. Applying hardening flags to a package does not require rebuilding GCC, and hardening the compiler process does not automatically enable hardening in the programs it emits.

## 2. Build reference callers

Run after the full callers and both library/dependency arms exist. These compile the **same sources and workloads** with reference executable flags. The primary comparison includes caller hardening as well as library hardening; later library scope retains the full caller. The MPI versions/headers/options are identical across arms. Both arms use RUNPATH, allowing the explicitly selected runtime libraries to take precedence; the loader checks below reject a substitution.

```bash
source "$TRIAL_ROOT/env.sh"
source "$TRIAL_ROOT/profiles.sh"
profile_flags reference
read -r -a cargs <<< "$EXE_CFLAGS"
read -r -a fargs <<< "$EXE_FFLAGS"
read -r -a largs <<< "$EXE_LDFLAGS"
for package in fftw hdf5 lapack fftw-mpi hdf5-mpi; do
    test ! -e "$TRIAL_ROOT/bench/$package-reference"
done
"$CC" "${cargs[@]}" -I "$TRIAL_ROOT/install/fftw/reference/include" \
  "$TRIAL_ROOT/bench/fftw_bench.c" -L "$TRIAL_ROOT/install/fftw/reference/lib" \
  -Wl,--enable-new-dtags -Wl,-rpath,"$TRIAL_ROOT/install/fftw/reference/lib" \
  -lfftw3_threads -lfftw3 -lm -lpthread "${largs[@]}" \
  -o "$TRIAL_ROOT/bench/fftw-reference"
"$CC" "${cargs[@]}" -I "$TRIAL_ROOT/install/hdf5/reference/include" \
  "$TRIAL_ROOT/bench/hdf5_bench.c" -L "$TRIAL_ROOT/install/hdf5/reference/lib" \
  -Wl,--enable-new-dtags -Wl,-rpath,"$TRIAL_ROOT/install/hdf5/reference/lib" \
  -lhdf5 -lm "${largs[@]}" -o "$TRIAL_ROOT/bench/hdf5-reference"
"$FC" "${fargs[@]}" "$TRIAL_ROOT/bench/lapack_bench.f90" \
  -L "$TRIAL_ROOT/install/lapack/reference/lib" -llapack \
  -L "$TRIAL_ROOT/install/blas/reference/lib" -lblas -Wl,--enable-new-dtags \
  -Wl,-rpath,"$TRIAL_ROOT/install/lapack/reference/lib" \
  -Wl,-rpath,"$TRIAL_ROOT/install/blas/reference/lib" \
  "${largs[@]}" -o "$TRIAL_ROOT/bench/lapack-reference"
activate_mpi_profile reference
profile_flags reference
read -r -a cargs <<< "$EXE_CFLAGS"
read -r -a largs <<< "$EXE_LDFLAGS"
"$MPI_PREFIX/bin/mpicc" "${cargs[@]}" -I "$TRIAL_ROOT/install/fftw-mpi/reference/include" \
  "$TRIAL_ROOT/bench/fftw_mpi_bench.c" -L "$TRIAL_ROOT/install/fftw-mpi/reference/lib" \
  -Wl,--enable-new-dtags -Wl,-rpath,"$TRIAL_ROOT/install/fftw-mpi/reference/lib" \
  -lfftw3_mpi -lfftw3 -lm "${largs[@]}" -o "$TRIAL_ROOT/bench/fftw-mpi-reference"
"$MPI_PREFIX/bin/mpicc" "${cargs[@]}" -I "$TRIAL_ROOT/install/hdf5-mpi/reference/include" \
  "$TRIAL_ROOT/bench/hdf5_mpi_bench.c" -L "$TRIAL_ROOT/install/hdf5-mpi/reference/lib" \
  -Wl,--enable-new-dtags -Wl,-rpath,"$TRIAL_ROOT/install/hdf5-mpi/reference/lib" \
  -lhdf5 -lm "${largs[@]}" -o "$TRIAL_ROOT/bench/hdf5-mpi-reference"
source "$TRIAL_ROOT/mpi-env.sh"
```

Inspect ELF, commands and loaded dependencies for both callers using 01. Full callers must have PIE/RELRO/NOW; reference callers must reflect the disabled controls. Upstream tools and MPI/UCX utilities need executable PIE qualification as well; a shared-library `-fPIC` setting alone is not that qualification. Retain any audit failure and resolve it before claiming the full installation satisfies the specified profile.

### Freeze a build inventory

After all qualification checks pass, create an inventory before timing. Regenerate it under a new filename after a documented rebuild; never edit a frozen experiment while its jobs are running.

```bash
python3 - <<'PYTHON'
import hashlib, json, os, pathlib
root=pathlib.Path(os.environ['TRIAL_ROOT'])
manifest=root/'logs/build-inventory.json'
if manifest.exists(): raise SystemExit('Inventory exists; retain it and use a new trial identity after a rebuild')
files={}
for base in (root/'install',root/'bench',root/'toolchains'):
    for path in sorted(base.rglob('*')):
        if path.is_file():
            files[str(path.relative_to(root))]=hashlib.sha256(path.read_bytes()).hexdigest()
manifest.write_text(json.dumps({'procedure_commit':os.environ.get('TRIAL_PROCEDURE_COMMIT',''),
                               'files_sha256':files},indent=2)+'\n')
PYTHON
```

## 3. Guard MPI dependencies on every rank

Generate this helper once. It runs before each timed MPI caller on each compute node. Its cost is included in whole-process time, symmetrically in both arms, and excluded from the caller's kernel timers. Report whole-process time as launch/loading/guards/workload/validation, not pure loader time. Matching launchers, selected package libraries and the UCX component are checked separately. The caller's MPI placement check remains active on every invocation.

```bash
cat > "$TRIAL_ROOT/bench/rank-exec.sh" <<'SH'
#!/bin/bash
set -euo pipefail
exe=${1:?executable}; shift
: "${TRIAL_MPI_PREFIX:?}" "${TRIAL_UCX_PREFIX:?}"
loaded=$(ldd "$exe")
component=$(ldd "$TRIAL_MPI_PREFIX/lib/openmpi/mca_pml_ucx.so")
export TRIAL_LOADED="$loaded" TRIAL_COMPONENT="$component"
python3 - <<'PY'
import os, re, socket
mpi,ucx=os.environ['TRIAL_MPI_PREFIX'],os.environ['TRIAL_UCX_PREFIX']
text=os.environ['TRIAL_LOADED']+'\n'+os.environ['TRIAL_COMPONENT']
if 'not found' in text: raise SystemExit('Missing rank dependency')
mpi_paths=re.findall(r'lib(?:mpi|open-rte|open-pal)\S*\s+=>\s+(\S+)',text)
ucx_paths=re.findall(r'lib(?:ucp|uct|ucs|ucm)\S*\s+=>\s+(\S+)',text)
if not mpi_paths or any(not p.startswith(mpi+'/lib/') for p in mpi_paths):
    raise SystemExit('Wrong MPI on rank')
if not ucx_paths or any(not p.startswith(ucx+'/lib/') for p in ucx_paths):
    raise SystemExit('Wrong UCX component dependencies on rank')
package=os.environ.get('TRIAL_LIBRARY_PREFIX','')
if package:
    family='libfftw3' if '/fftw' in package else 'libhdf5'
    paths=re.findall(family+r'\S*\s+=>\s+(\S+)',os.environ['TRIAL_LOADED'])
    if not paths or any(not p.startswith(package+'/lib/') for p in paths):
        raise SystemExit('Wrong/mixed payload library on rank')
rank=os.environ['OMPI_COMM_WORLD_RANK']
print(f'TRIAL_RANK rank={rank} host={socket.gethostname()} mpi={mpi} ucx={ucx}',file=__import__('sys').stderr)
PY
unset TRIAL_LOADED TRIAL_COMPONENT
exec "$exe" "$@"
SH
chmod +x "$TRIAL_ROOT/bench/rank-exec.sh"
```

Record `ucx_info -d`, runtime tuning and memlock on all nodes for **both** stacks before timing. UCX transport capability must match; a reference TCP fallback versus full RDMA is a configuration error. Keep bindings, filesystem policy and inputs identical. Inspect Slurm allocation and placement evidence; do not accept oversubscription or a site MPI fallback.

## 4. Run and report the first comparison

After a correctness/placement pilot, use the fixed pair/allocation budgets in 08. For interactive runs in a compute allocation:

```bash
export TRIAL_SCOPE=stack COMPARATORS=reference PAIRS=10
# Use the serial or parallel launch commands in 06 with a fresh RUN_ID.
# For manual paired.py calls, also provide its reference executable:
export COMPARE=reference
export COMPARE_EXECUTABLE="$TRIAL_ROOT/bench/fftw-reference"
# Unset MPI_NP for this serial example and use an allocated CPUSET.
unset MPI_NP
taskset -c "$CPUSET" python3 "$TRIAL_ROOT/bench/paired.py" \
  fftw "$TRIAL_ROOT/bench/fftw-fixed" stack-fft-small 1 1024 50000 1 estimate
unset COMPARE_EXECUTABLE
```

For the batch campaign set `TRIAL_SCOPE=stack`, `RUN_PIE=0`, `CAMPAIGN_COMPARATORS=reference`, `NODE_COUNTS='1 2'`, `RUN_WEAK=0`. The normal workload suite includes startup cases; the initial primary comparison already changes the callers' PIE together with their other controls. PIE-only attribution is deferred. Summaries/CSV label `scope=stack`, identify callers, dependency prefixes and launchers by arm, and retain absolute runtimes, paired changes, means/spread and intervals. Keep allocations separate and report coverage/failures.

For a focused package/control follow-up select `TRIAL_SCOPE=library`; retain full MPI/UCX and full BLAS, build only the missing package variants, then choose workload/comparator entries through 06. Set `RUN_PIE=1` and build 07 callers only when conducting PIE attribution. Removal arms are experimental references, not a proposed production relaxation or an automatic compliance exception.

The first comparison measures the combined trial scope. It does not attribute a change to MPI versus UCX or a particular flag, and it does not establish that all applications/scales are unaffected. Expansion follows the predeclared hypotheses and uncertainty, not a requirement to test every possible combination.
