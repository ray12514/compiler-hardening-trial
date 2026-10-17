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
comparison was not yet implemented at the handoff. The follow-up below now
provides it through `--scope deployment`; existing `stack` results retain their
original scope. It requires no individual flag removals.

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
5. Use the implemented fixed-caller deployment comparison below and select a
   representative site application with realistic inputs and checkpoint cadence.
   Agree on a practically meaningful overhead threshold and required precision
   before confirmation sampling. Individual-flag attribution remains deferred.

## 9. Next phase: executable workflow assessment

The purpose is to assess supplied libraries with an ordinarily compiled caller,
using a controlled representation of the site's workload. A complete CFD or
LAMMPS build is optional later confirmation; it is not required to make this
measurement useful. Do not expand into unrelated software to force a slowdown.
Do not reinterpret small negative estimates as a demonstrated speed benefit.

### Implemented interfaces

| Interface | Behavior |
|---|---|
| `trial production --scope deployment` | Compile one reference caller, run its identical binary/hash with the two compatible complete library stacks; retain both library build identities |
| `--scope stack` | Retain matched full/reference callers for the earlier whole-stack question; this remains the backward-compatible default |
| `--reframe` | Use one serial, allocation-local ReFrame check to run the existing controller; record per-condition performance metrics and original result location |
| `--fields 3 --fft-plan measure` | Three independently persistent fields with reused measured forward/inverse plans; each checkpoint contains a dataset per field |
| `--steps N` | Freeze the iteration count rather than calibrating different counts by layout; stop partial if declared write allowance cannot fit, without silently reducing work |
| `--overhead-limit-percent P` | Compare the paired interval with a predeclared practical limit; unresolved and incomplete are explicit outcomes; no limit is guessed by default |

The installer copies these sources and the new ReFrame adapter. It does not
change completed package builds, old callers, old results, profile vectors or
numbered build/measurement recipe blocks. New source hashes produce new caller
identities. `--report` can still regenerate old production exports without MPI,
Slurm or new measurements; old scope and field-count defaults remain readable.

### Ordered work and gates

1. **Evidence review and artifact verification.** Retain today's original result
   folders and examine raw complete pairs and uncertainty. The next driver run
   verifies completed artifact hashes, records both stack identities and
   effective flag vectors, and inspects installed ELF libraries for RELRO/NOW
   and canary/fortified-call symbols. Requested linker protections must be
   present. Symbol observations alone do not quantify hardening coverage.
2. **Existing-allocation audit.** Reuse the physical-core/WEKA and memory checks.
   Keep the interactive Slurm overlap setting that qualified on the site, with
   private launchers, RC/shared-memory UCX policy and no rank oversubscription.
   Each rank records its actual binding, caller SHA-256 and loaded library paths.
3. **Short fixed-caller workflow pilot.** Start at one and two nodes, 16 physical
   cores per node, four process pairs, three fields and a fixed global shape.
   Use the README's bounded command. Check both ordinary FFT loops and
   integrated checkpoints plus the standalone collective/independent I/O cases.
   Four pairs establish runnable settings, not an acceptance conclusion.
4. **Representative work definition.** Record the intended transform dimensions,
   field count, real/complex requirements, plan reuse and checkpoint pattern.
   The implemented baseline is complex-to-complex distributed 3D FFTW with
   sequential fields, a simple spectral multiplier, contiguous per-field HDF5
   datasets, one replacing checkpoint file and a final warm read-back. It is
   not a fluid solver and does not implement LAMMPS's complete local-FFT/remap
   path. Real transforms, batched local transforms, chunked/compressed output
   or retained checkpoint history require explicit future extensions if the
   selected site's workflow needs them; do not label them covered now.
5. **Density and scale.** Use all audited eligible physical cores on one/two
   nodes with bounded per-field memory and I/O. Run four and eight nodes
   separately after costs are known so the missing large condition is not
   starved by earlier cases. Keep fixed-global-shape and per-rank-volume
   experiments separate. Never combine today's matched-caller results with
   the new deployment scope as one estimate.
6. **Confirmation and interpretation.** Agree on the practical overhead limit,
   sampling precision and workload first. Use balanced fresh-process pairs
   (20 is a starting sample count, not a guarantee of precision) and selected
   repeats in independent allocations. Keep partial conditions visible.
   ReFrame completion is not performance acceptance. The reporting assessment
   applies to an individual completed condition and does not replace deployment
   evidence or independent repeats. It does not measure the security benefit.

### Optional OSU communication baseline

Bring in a small CPU-only OSU subset as a supplementary MPI diagnostic:

| Benchmark | Initial placement | Question |
|---|---|---|
| `osu_latency` | Exactly two ranks, one per selected node | Does small-message point-to-point latency differ? |
| `osu_bw` | Exactly two ranks, one per selected node | Does sustained point-to-point bandwidth differ? |
| `osu_alltoall` | The qualified workload density | Does collective data exchange differ at that rank count? |
| `osu_allreduce` | The same density | Does reduction/synchronization latency differ? |

Use one fixed ordinary caller per benchmark, a pinned released OSU version and
the compatible reference/full MPI/UCX runtimes. Match message sizes, warmups and
iterations; record binding, versions and loaded paths; bound all-to-all memory
against communicator size. Preserve latency and bandwidth units and directions.
OSU's repeated internal operations are not independent observations; fresh
process pairs provide the paired samples. A later `osu_mbw_mr` can examine
simultaneous pairs if two-rank bandwidth does not explain dense behavior.

The OSU adapter is planned, not shipped in this update. Prepare its source and
offline build outside the timed allocation when adopted. It is not a dependency
of the new driver/ReFrame workflow and cannot substitute for FFTW/HDF5 evidence.
Do not install MVAPICH just to obtain OSU; its MPI benchmarks can use Open MPI.
[Official benchmark descriptions and release list](https://mvapich.cse.ohio-state.edu/benchmarks/)

The copy-and-paste run sequence, result paths and new options are in the
[next-session workflow](README.md#next-session-fixed-caller-application-pattern-assessment).

### Implementation validation

The follow-up passed 68 automated checks, including real ReFrame 4.10.4
completion/partial-result checks with synthetic fixtures. The updated C caller
compiled with `-Wall -Wextra -Werror` against cached Linux MPI/FFTW/HDF5 libraries.
Twenty-four isolated local MPI runs exercised one/two/four ranks, three fields,
both planning policies and all four workload modes; numerical/restart checks,
per-rank/per-field I/O records and file cleanup passed. These are functional
checks using a network-disabled container, not Slurm/RDMA or performance
qualification on the target cluster. No new target-system campaign was launched.
