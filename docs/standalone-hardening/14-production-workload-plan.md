# Production workload comparison: implementation plan

Status: the first production runner and sustained callers are implemented;
target Slurm/WEKA/fabric qualification and production measurements remain to run.
Use the [runnable workflow](README.md#after-the-pilot-run-production-density-workloads).
Scope agreed: 2026-10-16; complete-profile production assessment before attribution.
The existing package pilot is a screening and qualification stage. The next stage
will compare the complete hardened stack with its complete reference using dense
MPI placement, sustained work and repeated checkpoints. Individual compiler flag
removal, package attribution and alternative hardening profiles remain deferred.

## 1. Questions and scope

Measure whether hardening changes elapsed time, useful throughput, memory use or
variability for realistic resource occupancy and data movement. Report absolute
seconds and percentage differences, including uncertainty and observed variation
between host groups. Establish repeatability before interpreting a small effect.

Three workload families will separate sustained FFT, sustained parallel HDF5 and
an integrated FFT/checkpoint loop. The integrated case is a mini-application
analogue, not a CFD solver or evidence for every application. A representative
site application with its real inputs is the later validation gate.

A result compatible with zero difference does not prove zero overhead. Before
confirmation sampling, select a practically meaningful slowdown threshold and
desired interval width. Security benefits need a separate threat-model assessment;
performance measurements alone cannot decide whether a protection is worthwhile.

## 2. P0: remove limits before increasing rank density

The screening [MPI callers](05-parallel.md) and `trial test` retain their original
limits. The separate `trial production` command addresses these gaps without
changing those completed build identities:

| Current behavior | Required change |
|---|---|
| Driver and allocation controller accept one or four ranks per node | Accept validated positive counts and an allocated-physical-core mode |
| Core binding has no explicit WEKA reservation audit | Discover service reservations per host and verify their exclusion from every rank's affinity |
| FFT caller accepts cubic dimensions only, at most 256 | Support explicit dimensions, safe larger sizes, checked arithmetic and memory estimates |
| FFT caller rejects empty local slabs | Keep this guard; add a collective preflight explaining incompatible geometry before measurements |
| FFT caller repeats forward transforms of fixed input | Add persistent, numerically stable iteration state and a forward/inverse workload with plan reuse |
| HDF5 caller writes and immediately reads one dataset | Add repeated checkpoints, selectable cadence, retention and separately labeled restart reads |
| HDF5 request records collective/independent selection | Record actual modes and fallback causes on every rank |
| Pilot exports phase summaries | Add job-level timing, work counts, checkpoint history and a consolidated campaign export |

Keep existing screening recipes, caller binaries and result identities unchanged.
Compile new full/reference callers under distinct target names and workload hashes;
reuse the unchanged matching libraries and archive new calibration separately.
No completed package build should be invalidated solely to change placement or
analysis. Newly compiled callers must still use the matching arm's libraries.

## 3. Placement and geometry contract

Use one MPI rank per **allocated physical core** for the primary dense lane, with
one thread per rank and explicit core binding. Discover topology and allocation
limits on every selected host; do not derive this from a one-CPU interactive shell
or an already core-bound rank, or assume Slurm CPU counts mean physical cores.
Check allocation-wide resources, slots, allowed CPU
masks and physical-core identities together. Open MPI distinguishes slots from
hardware resources and supports explicit mapping/binding and binding reports.
[Open MPI 4.1.8](https://www.open-mpi.org/doc/v4.1/man1/mpirun.1.php),
[Slurm CPU allocation and binding](https://slurm.schedmd.com/cpu_management.html)

### Eligible cores and WEKA reservations

For the first density progression, use **16, then 32, then all eligible physical
cores per node**, subject to allocation capacity, FFT geometry, memory and run
budget. `trial production` accepts these counts and `all`; the screening
`trial test` command still accepts only one or four. The primary dense lane uses the production
core budget rather than stop at 16 ranks. If 92 physical cores are already usable
by the job after reservations, the final target is 92 ranks per node. If 92 is the
hardware count before reservations, determine the smaller eligible count first.

Discover the actual WEKA reservation on **each selected host**; the tentative
CPU range 19–22 is not configuration. Inspect the client resource assignments and
its dedicated cgroup, and cross-check Slurm's service-core reservation. Reconcile
OS CPU IDs with socket/core topology and Slurm's numbering before comparing masks.
Exclude every SMT sibling of a reserved physical core. WEKA documents cgroup
v1/v2 inspection and warns about CPU index mismatches.
[WEKA CPU allocation guidance](https://docs.weka.io/best-practice-guides/weka-and-slurm-integration/avoid-conflicting-cpu-allocations)

The placement preflight must:

1. Resolve the selected job/step's actual cgroup and effective CPU allowance on
   every host. A service-level or root cgroup is not proof of this job's grant.
   For cgroup v2 use `cpuset.cpus.effective`; an empty configured `cpuset.cpus`
   can inherit a parent's allowance. Discover paths rather than assume a fixed
   WEKA or Slurm cgroup path.
   [Kernel cpuset interface](https://cdn.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html#cpuset)
2. Intersect online CPUs with the job's allowed CPUs, subtract verified service
   reservations expanded to whole physical cores, then select one hardware
   thread per remaining core. Honor task slots as a separate constraint.
   A broad inherited WEKA allowance is not evidence that every listed CPU is a
   dedicated WEKA core; resolve ambiguous reservations before a dense run.
3. Choose explicit per-host maps with a recorded socket/NUMA distribution. Use
   the same maps for full and reference, and verify actual rank affinity before
   timing. Reject shared physical cores and intersections with reserved cores.
   Apply this policy to serial caller placement as well as MPI placement.
4. Save requested and observed masks, reservation evidence and eligible physical
   core counts in the local manifest. Do not assume all hosts reserve the same
   CPU IDs. Stop qualification if the requested density cannot be verified;
   never silently use reserved cores or reduce only one comparison arm.

This is a read-only discovery and benchmark-placement change. It does not modify
WEKA mounts, services or Slurm configuration. Existing pilot results have no
explicit WEKA-exclusion evidence; audit saved affinities where available and
otherwise label their reservation status unverified.

### Rank and thread policy

Reject unintended rank/core sharing, ranks outside selected hosts, mixed hardware
groups, unavailable task slots and hidden threaded BLAS/FFT oversubscription.
If the current job grants fewer slots/cores than this lane needs, record the
capacity limit and obtain an appropriate later allocation; node count alone
does not authorize using every physical core present on the hardware.
Carry the already qualified private MPI/UCX paths, component policy, RDMA-only
transport settings and interactive Slurm overlap policy into every arm and scale.
Overlap permits launching within the interactive allocation; it does not grant
extra cores. Do not enable rank oversubscription to bypass allocation checks.

Pure MPI is the first controlled lane, not a claim that all users run this way.
Keep OpenMP and threaded numerical libraries at one thread per rank for this
lane; do not count SMT threads as additional physical cores. In a hybrid layout,
MPI communicates between nodes and threads execute within each rank on a node.
If a target application uses MPI plus threads, add a separately labeled hybrid
lane with explicit ranks, threads and disjoint core sets. Hold total allocated
cores constant when comparing layouts; verify the threaded library configuration.
The current MPI FFTW recipe enables threads, but a hybrid caller still needs
explicit FFTW thread initialization and verified MPI thread support; raising an
environment variable alone does not create this lane.
[FFTW MPI with threads](https://www.fftw.org/doc/Combining-MPI-and-Threads.html)

FFTW MPI uses a slab distribution along the first dimension. Require first
dimension `Nx >= total_ranks`, but also query every rank's actual local extent;
that inequality alone does not certify useful or balanced work. Prefer balanced
dimensions, including transpose stages, and enough work per rank to avoid a
communication-only toy. Use FFTW's distribution/allocation queries rather than a
hand-calculated slice size; transposes can require additional local storage.
For complex multidimensional FFTs, prefer a first dimension divisible by the
rank count and a product of remaining dimensions divisible by that count;
confirm actual local extents and balance rather than relying on that rule alone.
[FFTW data distribution](https://www.fftw.org/~fftw/doc/MPI-Data-Distribution.html),
[load balancing](https://www.fftw.org/fftw3_doc/Load-balancing.html)

Plan memory from each actual allocation query: the current caller owns three
complex arrays, plus FFTW plans/workspace, MPI buffers and runtime overhead.
Measure peak resident memory during calibration and reserve explicit node-memory
headroom. Never silently drop ranks with zero slabs or shrink only one arm.
If balanced slab geometry cannot meet memory and useful-work requirements at the
desired scale, reduce that scale and document the limit. Evaluate a pencil FFT
dependency only as a separately scoped extension; it changes the tested stack.

## 4. Workload definitions

**Sustained FFT:** create plans once, then run a fixed number of forward/operator/
inverse iterations with explicit normalization and bounded deterministic state
updates. Check
finite values and numerical error without adding a full new initialization to
every timed iteration. Preserve small-call cases separately. Record planning,
first iteration and steady iterations; vary global size for strong scaling and
per-rank volume for a separately defined weak-scaling lane. Keep the same layout,
planner policy, sizes, seeds and iteration count in both arms. FFTW's documentation
identifies slab geometry and transpose choices as performance-relevant; changing
those choices between arms would change the experiment.
[FFTW MPI performance tips](https://www.fftw.org/fftw3_doc/FFTW-MPI-Performance-Tips.html)

**Sustained HDF5:** repeatedly write distributed datasets with predeclared
checkpoint count and bytes per rank. Test collective and independent transfer
requests as separate conditions, initially using an uncompressed contiguous
layout. Add an application-motivated chunked layout only as a labeled condition.
Use deterministic data and collective correctness checks; reopen and verify a
checkpoint before deleting it, including restoring the integrated loop's state.
Respect collective metadata call requirements.
[Parallel HDF5 introduction](https://portal.hdfgroup.org/documentation/hdf5/latest/_intro_par_h_d_f5.html)

Query `H5Pget_mpio_actual_io_mode` and `H5Pget_mpio_no_collective_cause` after
transfers: a collective request can fall back, and ranks can report different
actual modes. Preserve those observations rather than labeling results only by
the requested mode.
[HDF5 transfer-property APIs](https://support.hdfgroup.org/documentation/hdf5/latest/group___d_x_p_l.html)

**FFT plus checkpoint loop:** reuse distributed state across iterations and write
an HDF5 checkpoint every fixed number of iterations. Start with two declared
cadences representing less-frequent and I/O-heavy checkpointing; derive their
work and data volumes from calibration and eventual site application evidence.
Time the entire fixed-work loop, including the chosen checkpoint completion
semantics. Include finalization separately in a launch-to-exit measurement.

Specify whether a checkpoint ends at write, flush or file close, and time the
selected boundary identically. HDF5 flushes its buffers and asks the OS to flush;
it does not itself control ultimate disk persistence. Do not claim crash-durable
storage without validating the filesystem and driver contract. Immediate readback
is a warm/restart scenario, not a cold-read bandwidth measurement.
[HDF5 file flush semantics](https://support.hdfgroup.org/documentation/hdf5/latest/group___h5_f.html)

Use unique checkpoint names and bounded retention, recording total bytes written
and peak retained bytes. Fix filesystem placement, striping settings where known,
cache policy and cleanup ordering across arms. Do not clear shared caches or
claim cold I/O based only on new filenames. Record contention indicators and
outliers; predeclare rerun/exclusion rules rather than deleting slow observations.

## 5. Calibration and bounded campaign

1. Audit available physical cores, binding, RDMA transport and memory at the new
   density on one and two nodes, for both stacks. Run correctness before timing.
2. Calibrate both stacks with bounded trials. Select equal dimensions, iteration
   counts, checkpoint bytes and cadence targeting roughly 30–120 seconds per
   initial fresh-process run. Freeze these settings before collecting comparisons;
   never stop each arm after equal walltime and compare unequal work.
3. Run the two-node full-density pilot first. Use measured durations and storage
   consumption to estimate the remaining allocation, including two arms per pair,
   launches, warmup, cleanup and a safety reserve. Report an affordable matrix.
4. Expand to four and eight nodes with limited rotated homogeneous host groups.
   Serial baselines visit selected hosts; do not exhaust all host permutations.
   Keep scaling and geometry compatible, and run I/O/network conditions sequentially
   so the campaign does not create competing benchmark traffic against itself.
5. Repeat selected conditions in later independent allocations. Host rotations and
   rounds within one reservation are useful coverage, not independent allocations.

Balance and randomize full/reference order within fixed host/configuration blocks.
Treat each fresh-process pair as the sampling unit; ranks and consecutive loop
iterations are correlated observations, not additional independent samples.
Retain individual iteration/checkpoint times for diagnosing drift and tails.
Predeclare an affordable pair count using pilot variability and the precision
target; any staged expansion follows a written budget/precision rule, not stopping
when a favorable significance result appears. Label multiple-case pilot findings
as exploratory and reserve confirmation samples for selected effects.

## 6. Measurements, accumulated cost and export

Primary outcomes are end-to-end fixed-work elapsed time and useful throughput.
Record the slowest-rank duration across the entire workload region and independent
controller launch-to-exit time; label initialization and validation inclusions.
Buffer rank-local phase observations and reduce/gather after the measured window;
do not print or gather every iteration or insert artificial phase barriers.
Phase max-rank times diagnose bottlenecks, but their maxima may belong to different
ranks: do not add them and call the sum the observed job critical path.

Export versioned `manifest.json`, raw fresh-pair CSV, iteration/checkpoint CSV and
summary CSV/JSON with absolute deltas, percent changes and paired uncertainty.
Include hashes, input/work counts, seeds, order, host-group aliases, topology,
affinity, ranks/threads, actual I/O modes, checkpoint bytes, RSS and launch policy.
Retain private paths/host identities locally; provide a shareable redacted export.
Automated plots show paired full/reference elapsed time, delta intervals by scale,
throughput, iteration/checkpoint trends and memory. Preserve failed/partial runs.

The frozen manifest specifies shape, ranks/threads/core maps, steps, checkpoint
cadence and count, retained byte budget, completion semantics, validation policy,
planner policy, seed, process-pair budget and timeout. Include observed useful
work/volume, not only requested settings. Optional read-only NIC/port counter
deltas can corroborate traffic, with unrelated traffic and counter units labeled;
logical FFT array bytes are not measured wire bytes.

Estimate accumulation only from representative nonoverlapping phases:
`delta_job = delta_startup + N_steps * delta_step + N_checkpoints * delta_checkpoint`.
Accumulation is additive, not exponential; do not multiply a measured whole-job
percentage by the iteration count or multiply walltime overhead by rank count.
Extra allocated core-hours can be reported separately from elapsed seconds.
This illustrative model assumes stable phase costs, fixed work/cadence and no
unmodeled overlap; avoid counting FFT or I/O twice inside `delta_step`. Validate
the prediction against the integrated loop. Do not multiply a microbenchmark
percentage by an arbitrary whole-job duration. Report measured seconds first,
then clearly labeled scenario estimates with uncertainty and assumptions.

## 7. Implementation and acceptance gates

| Milestone | Completion evidence |
|---|---|
| P0 placement and size validation | Per-host allocation/core/slot and WEKA reservation checks; one hardware thread per physical core; invalid geometry/overflow rejected before measurement; observed bindings exclude reserved cores in both arms |
| P1 sustained callers | Equal-work FFT, HDF5 and integrated loops pass correctness, timeout, cleanup and bounded-storage checks |
| P2 paired driver and exports | Reproducible frozen manifest, balanced randomized order, raw data and job-level metrics; existing screening remains usable |
| P3 two-node dense pilot | Both stacks use intended libraries/fabric; no unintended oversubscription, empty slabs, memory failure or mislabeled I/O |
| P4 limited 4/8-node campaign | Fits measured time/storage budget; host/group effects retained; plots regenerate from saved data |
| P5 application confirmation | A named site application, representative input and checkpoint policy validate or bound the mini-application conclusions |

Advance only after the preceding gate passes. If the current reservation cannot
fit implementation, qualification and a defensible run budget, retain the pilot
data and schedule the dense campaign later rather than launching an unvalidated
full-core sweep. A threshold-compatible result supports only the tested workload,
scale and environment; report uncertainty when a decision remains unresolved.

## 8. Session handoff — 2026-10-16

Testing stopped at the operator's request; resume the assessment next session.
No additional benchmark runs or individual-flag experiments are requested now.
The current runner includes Slurm affinity-only allocation discovery and WEKA
reservation checks. Preserve the existing trial root and completed package
installations, configuration, build records and results.
The [three-page session report](../../output/pdf/compiler-hardening-session-report-2026-10-16.pdf)
plots the screenshot-derived pilot and dense MPI estimates; its
[transcribed evidence](../../reports/2026-10-16/evidence.json) is kept separately
from original campaign exports.

### Evidence received so far

These are rounded transcriptions from operator-supplied screenshots, not an
analysis of the original raw results. Positive change means full was slower.
Keep each layout, host group and allocation separate in the analysis.

| Layout | Completed paired coverage | Observed runtime changes |
|---|---|---|
| 2 nodes, 16 ranks/node | 10/10 pairs for all four production conditions | FFT +0.22%; collective HDF5 -1.08%; independent HDF5 approximately 0%; integrated loop -2.59% |
| 2 nodes, 92 ranks/node | 10/10 pairs for all four conditions | FFT +0.40%; collective HDF5 +0.33%; independent HDF5 +0.91%; integrated loop +0.02% |
| 4 nodes, full eligible-core layout | 10/10 pairs for all four conditions | FFT -1.29%; collective HDF5 -0.45%; independent HDF5 +1.32%; integrated loop -2.60% |
| 8 nodes, full eligible-core layout | FFT 4/10 pairs; campaign budget exhausted | FFT -1.56%; no completed paired HDF5 or integrated-loop results shown |

The earlier all-package screening pilot also reported complete coverage. The
defensible provisional finding is **no consistent performance penalty detected
in the completed tested conditions**. Small negative estimates do not establish
that hardening improves performance. The eight-node result is preliminary, and
the final screenshot does not expose every confidence-interval bound clearly.
Do not pool the partial eight-node data with completed smaller layouts or count
reprinted copies of one summary as independent repetitions.

### Deployment question raised by the operator

The supplied libraries may be hardened while user applications retain their
ordinary compiler flags. The current production comparison changes both the
caller and its matching library/dependency stack between full and reference.
It therefore does not isolate this exact deployment combination, and a near-zero
combined effect does not bound every individual contribution.

Plan a **fixed reference caller with switched complete library/dependency
stacks**: use the same ordinarily compiled executable against the reference
libraries and against the hardened libraries, with the same work, binding and
runtime policy. Keep MPI/UCX consistent with the selected library stack and
verify actual loaded paths on every rank. Preserve ABI/toolchain compatibility
and account for compile-time header/inlined code in the fixed caller. This
comparison is not yet implemented by `trial production`; its existing `stack`
results must keep their original scope. It requires no individual flag removals.

Hardening compiled into a shared library does not automatically apply those
compiler options to an application's own code. Some checks, including fortified
libc call sites, depend on how the calling source was compiled; the scope must
be recorded explicitly.
[GCC instrumentation](https://gcc.gnu.org/onlinedocs/gcc-12.5.0/gcc/Instrumentation-Options.html),
[glibc source fortification](https://sourceware.org/glibc/manual/latest/html_node/Source-Fortification.html)

### Next-session order

1. Obtain the original result folders, including `manifest.json`, layouts,
   qualification/build identities, raw per-launch JSON, `pairs.csv`,
   `iterations.csv`, `io-modes.csv` and summaries. Keep private system evidence
   local; share the metric-only exports for analysis.
2. Confirm the effective flags and compiled artifacts for both arms, loaded
   libraries, observed bindings, equal work within pairs, completed coverage,
   achieved durations, budget caps and actual HDF5 I/O modes. Separate loop
   walltime from whole-process launch/guard/planning/validation time.
3. Inspect paired timing variation and order effects, especially variable
   reference integrated-loop timings and independent I/O. Retain slow samples;
   do not remove them because they change the conclusion. Regenerate intervals
   from complete pairs, with incomplete pairs and conditions explicitly marked.
4. Use the recorded eight-node work definition to choose the next frozen run;
   complete the missing eight-node evidence, then repeat selected conditions
   in an independent allocation. Do not silently combine different iteration
   counts, geometries or I/O-budget caps as one experiment.
5. Implement the fixed-caller deployment comparison above and select a
   representative site application with realistic inputs and checkpoint cadence.
   Agree on a practically meaningful overhead threshold and required precision
   before confirmation sampling. Individual-flag attribution remains deferred.
