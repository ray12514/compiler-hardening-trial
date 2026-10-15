# Standalone compiler hardening performance trial

| Document control | Value |
|---|---|
| Date | 2026-10-06 |
| Status | Proposed experiment; no local performance measurements yet |
| Purpose | Evidence for a security review of compiler hardening and HPC performance |
| Build method | Upstream source builds with GCC 12.5.0 and fixed Open MPI 4.1.8 + UCX 1.16.0; outside Spack |

The trial measures the incremental cost of compiler hardening on FFT, I/O, and numerical software. Published measurements and their limits are recorded in [the companion evidence note](standalone_compiler_hardening_performance_evidence_v1.md).

The executable procedures are in the [standalone runbooks](standalone-hardening/README.md), including GCC bootstrap when 12.5 is absent, package builds, fixed callers, MPI/UCX qualification, and [ReFrame execution/reporting](standalone-hardening/06-reframe.md). The [Slurm campaign](standalone-hardening/08-slurm-campaign.md) specifies hypotheses, complex serial/threaded/MPI FFTs, small-dataset and bulk HDF5 I/O, LU solve, short process/PIE comparisons, and 1/2/4/8-node runs. Real FFTs, QR/eigensolvers, compressed I/O and full application cases remain later coverage extensions.

## Package and compiler selection

| Package | Direct build | Representative measurements |
|---|---|---|
| FFTW 3.3.11 | Upstream `configure` / `make`, explicitly selecting GCC 12.5 and release flags | Planning time separately from repeated transform execution; real and complex 1D/3D transforms; small and large sizes; serial, threads, and MPI |
| HDF5 2.1.0 | Upstream CMake build of the C library; serial first, then parallel with fixed Open MPI + UCX | Contiguous bulk read/write, chunked data, many small datasets and metadata operations, file open/close, and representative MPI rank counts |
| Netlib LAPACK 3.12.1 | Upstream CMake build using GFortran 12.5 | LU/QR factorization and a representative eigensolver; include small and large matrices and numerical residuals |

Use GCC 12.5.0 for this experiment, matching the trials. Assume it is absent and follow the bootstrap or compatible transferred-toolchain route. Payload builds use the installed GNU drivers directly; MPI wrappers must invoke those drivers. Any later compiler-family comparison needs its own optimized reference and hardened pair.

These versions match the current trial roster; they are fixed experiment inputs, not a request to select newer upstream versions. Direct source builds need upstream-supported options. For the parallel HDF5 I/O case, start with the C interface: upstream HDF5 documents restrictions on combining parallel builds and its C++ interface. Do not copy the full Spack variant string into CMake. [HDF5 CMake build guidance](https://github.com/HDFGroup/hdf5/blob/develop/docs/INSTALL_CMake.md).

## Build comparison

Start with two separately configured build directories and installation prefixes per package and compiler:

* **A: optimized reference.** Explicit release optimization and CPU/SIMD settings, with the controls under test disabled or absent as verified for that compiler.
* **B: intended hardened release.** The same release settings plus the explicit, supported hardening set being evaluated.

Start with the supplied GNU/glibc list in [01](standalone-hardening/01-common.md): `-fstack-protector-strong`, C/C++ `-D_FORTIFY_SOURCE=2`, `-Wl,-z,relro`, and `-Wl,-z,now`. Executables use `-fPIE -pie`; shared libraries retain PIC in both arms. [07](standalone-hardening/07-consumer-pie.md) measures PIE separately. The earlier all-function/FORTIFY-3/stack-clash/initialization/CET set is available as an explicitly separate extended experiment. These flags alone do not establish an organizational requirement or STIG compliance. [GCC instrumentation options](https://gcc.gnu.org/onlinedocs/gcc-12.5.0/gcc/Instrumentation-Options.html), [glibc fortification](https://sourceware.org/glibc/manual/latest/html_node/Source-Fortification.html), [GNU linker options](https://sourceware.org/binutils/docs/ld/Options.html).

Use the compiler's documented spelling in each language. Do not pass `_FORTIFY_SOURCE` to Fortran as evidence of array protection. Unsupported controls are recorded as compatibility results rather than silently omitted from a build labelled fully hardened.

Compiler or distribution defaults can already enable hardening. Omitting extra flags is therefore insufficient to prove that A lacks the control. Inspect the actual commands and generated code or ELF properties; use documented disable options when the intended comparison requires them. Preserve PIC for shared-library linkage and record any protections retained in both arms. The conclusion must name the exact delta measured.

Compare B with independent variants that each remove one control from B. An optional `stack-all` contrast adds all-function stack protection to the supplied strong-stack profile. Sanitizers and controls requiring another compiler are separate experiments. GCC 12.5 has no `-fhardened`; use the explicit qualified flags.

Keep source checksum, dependency versions and paths, compiler, optimization, CPU target, SIMD, LTO, precision, threads, rank layout, and static/shared linkage identical within each pair. If only the package's rebuild is being evaluated, hold external MPI, compression, and BLAS providers fixed and record that scope. Rebuilding the dependency closure is a different experiment.

## Measurement controls

**FFTW:** preserve SIMD enablement and array alignment, use identical inputs, sizes, precision, thread count, and planning rigor. Measure planning separately. First use a deterministic planning mode to examine execution, then evaluate normal measured planning as a separate scenario. Record/clear wisdom consistently: a changed plan or inherited wisdom can confound a build comparison. FFTW documents how [planning modes select algorithms](https://www.fftw.org/doc/Planner-Flags.html) and how [compiler and SIMD options are supplied to its source build](https://www.fftw.org/doc/Installation-on-Unix.html).

**HDF5:** use identical dataset shapes, chunking, compression, filesystem location, MPI-IO settings, file sizes, and rank placement. Exercise the actual filesystem, and add a clearly labelled memory-backed or local-storage case to make CPU overhead visible when remote storage latency would mask it. Report cache conditions; elapsed buffered-write time alone does not establish durable-storage throughput. Keep synchronization and flush/close behavior identical. Measure startup and open/close separately from sustained transfer. The HDF Group provides [parallel I/O performance tools](https://docs.hdfgroup.org/archive/support/HDF5/doc/Tools/h5perf_parallel/h5perf_parallel.pdf) and describes [parallel I/O tuning factors](https://support.hdfgroup.org/documentation/hdf5-docs/hdf5_topics/ParallelHDF5.html).

**LAPACK:** keep the BLAS implementation and thread settings fixed. Inspect final linkage so a Cray wrapper does not change which BLAS supplies the hot kernels. Vendor BLAS can dominate a factorization, reducing how much the experiment measures the rebuilt LAPACK routines. If the reference BLAS is also rebuilt, explicitly include it in the measured scope. [Netlib explains BLAS's role in LAPACK performance](https://www.netlib.org/lapack/).

For all packages, run correctness checks first. Warm up, pin placement and affinity, and perform paired A/B runs in randomized or alternating order on the same allocation. Start with ten independent pairs as a pilot; use observed variability and the agreed regression limit to decide whether more runs are needed. Avoid simultaneous A and B jobs competing for resources. A clock or placement change is an experimental condition, not flag overhead.

The benchmark driver can itself change with hardening. For kernel/library attribution, keep the measurement driver constant and switch only its linked library. Add a deployment-shaped comparison with both the library and consuming executable hardened when evaluating executable PIE, startup, or the complete release profile. Verify the loaded library paths in every arm.

## Result and acceptance record

Agree on acceptable regression by workload before looking at results. There is no universal percentage in this proposal. Report both the estimated change and its uncertainty; failure to detect a statistically significant slowdown does not establish that a meaningful regression is absent.

* Elapsed-time increase: `100 * (time_B / time_A - 1)`.
* Throughput loss: `100 * (1 - throughput_B / throughput_A)`.
* Report individual paired measurements, a summary ratio with a confidence interval, correctness/residual checks, planning/startup separately, and workload conditions.
* A claim that overhead is below the agreed limit requires measurements precise enough that the upper bound on the slowdown is below that limit. Otherwise report the result as inconclusive and improve the experiment.

Retain source identities, compiler/module inventory, actual compile and link commands, dependency and runtime-library paths, artifact checks, test inputs, raw timings, summary method, and decisions. Standalone results apply to the recorded source build; a later Spack build needs confirmation that it emits the same relevant settings and behaves comparably.
