# 04 — LAPACK 3.12.1 with GCC 12.5.0

**Normal route:** follow the [README](README.md), then run `"$TRIAL_ROOT/runner/trial" build lapack`. The driver runs the applicable blocks below in child shells, including prerequisites. These numbered sections are recipe references; do not paste all of them after using the driver.

Prerequisites: [00](00-gcc-bootstrap.md) and [01](01-common.md). Run in Bash. Scope: shared, 32-bit integer API, all standard precisions built, bundled reference BLAS built with matching full/reference profiles. LAPACK itself is not an MPI implementation; the Open MPI/UCX installation is used by FFTW/HDF5, not injected into LAPACK's serial numerical comparison.

## 1. Build matching reference-implementation BLAS variants

This initial foundation build installs LAPACK too, but only its BLAS is used by the later matrix. Its full/reference builds use the same optimized reference implementation. The stack comparison selects the matching BLAS; later LAPACK-only comparisons keep full BLAS fixed. It is a reference implementation, not a vendor-optimized BLAS performance prediction. See [LAPACK's CMake options](https://github.com/Reference-LAPACK/lapack/blob/v3.12.1/CMakeLists.txt).

```bash
source "$TRIAL_ROOT/env.sh"
source "$TRIAL_ROOT/profiles.sh"
LAPACK_SOURCE="$TRIAL_ROOT/src/lapack-3.12.1"
BLAS_VARIANTS=(full reference)
for p in "${BLAS_VARIANTS[@]}"; do
export BLAS_PREFIX="$TRIAL_ROOT/install/blas/$p"
profile_flags "$p"
build="$TRIAL_ROOT/build/blas-$p"
test ! -e "$build"
    test ! -e "$BLAS_PREFIX"
mkdir -p "$TRIAL_ROOT/logs/blas/$p"
"$CMAKE" -S "$LAPACK_SOURCE" -B "$build" -G 'Unix Makefiles' \
  -DCMAKE_C_COMPILER="$CC" -DCMAKE_Fortran_COMPILER="$FC" \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_FLAGS="$CFLAGS" -DCMAKE_C_FLAGS_RELEASE='' \
  -DCMAKE_Fortran_FLAGS="$FFLAGS" -DCMAKE_Fortran_FLAGS_RELEASE='' \
  -DCMAKE_SHARED_LINKER_FLAGS="$SHARED_LDFLAGS" \
  -DCMAKE_EXE_LINKER_FLAGS="$EXE_LDFLAGS" \
  -DCMAKE_INSTALL_PREFIX="$BLAS_PREFIX" -DCMAKE_INSTALL_LIBDIR=lib \
  -DBUILD_SHARED_LIBS=ON -DBUILD_TESTING=ON -DCMAKE_EXPORT_COMPILE_COMMANDS=ON \
  -DUSE_OPTIMIZED_BLAS=OFF -DUSE_OPTIMIZED_LAPACK=OFF \
  -DBUILD_INDEX64=OFF -DBUILD_INDEX64_EXT_API=OFF -DLAPACKE=OFF -DCBLAS=OFF \
  2>&1 | tee "$TRIAL_ROOT/logs/blas/$p/configure.log"
"$CMAKE" --build "$build" --parallel "$JOBS" --verbose \
  2>&1 | tee "$TRIAL_ROOT/logs/blas/$p/build.log"
"$CTEST" --test-dir "$build" --output-on-failure --parallel "$JOBS" \
  2>&1 | tee "$TRIAL_ROOT/logs/blas/$p/check.log"
"$CMAKE" --install "$build" 2>&1 | tee "$TRIAL_ROOT/logs/blas/$p/install.log"
test -f "$BLAS_PREFIX/lib/libblas.so"
sha256sum "$BLAS_PREFIX/lib/libblas.so" > "$TRIAL_ROOT/logs/blas/$p/library.sha256"
done
export BLAS_PREFIX="$TRIAL_ROOT/install/blas/full"
```

Check the upstream numerical test summary as well as CTest status. Some LAPACK test programs write numerical failures in their output; a process exit alone is insufficient. Retain and inspect `Testing/Temporary/LastTest.log` and the upstream Python summary tests when available.

## 2. Build LAPACK against its matching BLAS

For the listed `full` set, [01](01-common.md) generates **`-fPIC -fstack-protector-strong`** in `FFLAGS` and **`-Wl,-z,relro -Wl,-z,now`** in `SHARED_LDFLAGS`. The CMake arguments below pass them explicitly. `_FORTIFY_SOURCE` does not add Fortran array bounds protection and is not applied to LAPACK's Fortran source. The fixed solve executable uses **`-fPIE`** and **`-pie`**, with its PIE comparison in [07](07-consumer-pie.md).

Start with `full reference`. Later select missing entries from `LAPACK_PROFILES`. FORTIFY and automatic C/C++ initialization removal are omitted because they do not protect Fortran LAPACK operations. CBLAS/LAPACKE bindings are a separate experiment.

```bash
LAPACK_VARIANTS=(full reference)
for p in "${LAPACK_VARIANTS[@]}"; do
    export BLAS_PREFIX="$TRIAL_ROOT/install/blas/full"
    if test "$p" = reference; then export BLAS_PREFIX="$TRIAL_ROOT/install/blas/reference"; fi
    profile_flags "$p"
    build="$TRIAL_ROOT/build/lapack-$p"
    prefix="$TRIAL_ROOT/install/lapack/$p"
    test ! -e "$build"
    test ! -e "$prefix"
    mkdir -p "$TRIAL_ROOT/logs/lapack/$p"
    declare -p FFLAGS SHARED_LDFLAGS BLAS_PREFIX > "$TRIAL_ROOT/logs/lapack/$p/flags.txt"
    "$CMAKE" -S "$LAPACK_SOURCE" -B "$build" -G 'Unix Makefiles' \
      -DCMAKE_C_COMPILER="$CC" -DCMAKE_Fortran_COMPILER="$FC" \
      -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_FLAGS="$CFLAGS" -DCMAKE_C_FLAGS_RELEASE='' \
      -DCMAKE_Fortran_FLAGS="$FFLAGS" -DCMAKE_Fortran_FLAGS_RELEASE='' \
      -DCMAKE_SHARED_LINKER_FLAGS="$SHARED_LDFLAGS" \
      -DCMAKE_EXE_LINKER_FLAGS="$EXE_LDFLAGS" \
      -DCMAKE_INSTALL_PREFIX="$prefix" -DCMAKE_INSTALL_LIBDIR=lib \
      -DCMAKE_INSTALL_RPATH="$BLAS_PREFIX/lib" \
      -DBUILD_SHARED_LIBS=ON -DBUILD_TESTING=ON -DCMAKE_EXPORT_COMPILE_COMMANDS=ON \
      -DUSE_OPTIMIZED_BLAS=OFF -DUSE_OPTIMIZED_LAPACK=OFF \
      -DBLAS_LIBRARIES:FILEPATH="$BLAS_PREFIX/lib/libblas.so" \
      -DBUILD_INDEX64=OFF -DBUILD_INDEX64_EXT_API=OFF -DLAPACKE=OFF -DCBLAS=OFF \
      2>&1 | tee "$TRIAL_ROOT/logs/lapack/$p/configure.log"
    "$CMAKE" --build "$build" --parallel "$JOBS" --verbose \
      2>&1 | tee "$TRIAL_ROOT/logs/lapack/$p/build.log"
    "$CTEST" --test-dir "$build" --output-on-failure --parallel "$JOBS" \
      2>&1 | tee "$TRIAL_ROOT/logs/lapack/$p/check.log"
    "$CMAKE" --install "$build" 2>&1 | tee "$TRIAL_ROOT/logs/lapack/$p/install.log"
    cp "$build/CMakeCache.txt" "$build/compile_commands.json" "$TRIAL_ROOT/logs/lapack/$p/"
    test -f "$prefix/lib/liblapack.so"
    ldd "$prefix/lib/liblapack.so" > "$TRIAL_ROOT/logs/lapack/$p/loaded.txt"
    readelf -lW "$prefix/lib/liblapack.so" > "$TRIAL_ROOT/logs/lapack/$p/elf.txt"
    readelf -dW "$prefix/lib/liblapack.so" >> "$TRIAL_ROOT/logs/lapack/$p/elf.txt"
done
```

Inspect each configure log for `BLAS supplied by user is WORKING`. Its `ldd` output must resolve BLAS to `BLAS_PREFIX`, not LibSci, MKL, OpenBLAS, or another variant. Verify both BLAS checksums after the matrix. Test-suite output needs the same numerical-failure review as the foundation build.

## 3. Create one fixed solve caller

This caller times `DGESV` (LU factorization plus solve) on a deterministic diagonally dominant matrix, with a known all-ones solution. Matrix initialization/copy and validation stay outside the timed region. It records the total kernel time over the requested repeats. Upstream tests cover wider numerical correctness; this caller is one workload, not the complete numerical trial suite.

```bash
cat > "$TRIAL_ROOT/bench/lapack_bench.f90" <<'F90'
program lapack_bench
  use iso_fortran_env, only: real64, int64
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
  implicit none
  integer :: n, repeats, i, j, r, info, stat
  integer, allocatable :: piv(:)
  integer(int64) :: t0, t1, rate
  real(real64), allocatable :: a0(:,:), a(:,:), b0(:), b(:)
  real(real64) :: elapsed, error, current
  character(64) :: arg
  external dgesv
  if (command_argument_count() /= 2) stop 2
  call get_command_argument(1,arg)
  read(arg,*,iostat=stat) n
  if (stat /= 0) stop 2
  call get_command_argument(2,arg)
  read(arg,*,iostat=stat) repeats
  if (stat /= 0) stop 2
  if (n < 2 .or. n > 4096 .or. repeats < 1) stop 2
  allocate(a0(n,n),a(n,n),b0(n),b(n),piv(n),stat=stat)
  if (stat /= 0) stop 2
  do j=1,n
    do i=1,n
      a0(i,j)=0.01_real64*sin(real(i+j,real64))
    end do
    a0(j,j)=a0(j,j)+real(n,real64)
  end do
  b0=sum(a0,dim=2)
  call system_clock(count_rate=rate)
  if (rate <= 0) stop 2
  elapsed=0.0_real64
  error=0.0_real64
  do r=1,repeats
    a=a0
    b=b0
    call system_clock(t0)
    call dgesv(n,1,a,n,piv,b,n,info)
    call system_clock(t1)
    if (info /= 0) stop 1
    elapsed=elapsed+real(t1-t0,real64)/real(rate,real64)
    if (.not.all(ieee_is_finite(b))) stop 1
    current=maxval(abs(b-1.0_real64))
    if (.not.(current <= 1.0e-10_real64)) stop 1
    error=max(error,current)
  end do
  write(*,'(a,es24.16,a,es24.16)') 'lu_solve,',elapsed,',',error
end program
F90
export BLAS_PREFIX="$TRIAL_ROOT/install/blas/full"
profile_flags full
read -r -a fargs <<< "$EXE_FFLAGS"
read -r -a largs <<< "$EXE_LDFLAGS"
"$FC" "${fargs[@]}" "$TRIAL_ROOT/bench/lapack_bench.f90" \
  -L "$TRIAL_ROOT/install/lapack/full/lib" -llapack \
  -L "$BLAS_PREFIX/lib" -lblas -Wl,--enable-new-dtags \
  -Wl,-rpath,"$TRIAL_ROOT/install/lapack/full/lib" -Wl,-rpath,"$BLAS_PREFIX/lib" \
  "${largs[@]}" -o "$TRIAL_ROOT/bench/lapack-fixed"
```

## 4. Measure and remove controls (optional attribution)

For the primary comparison, finish the builds and continue to 11/08 first. These manual timings use library-only scope and are available for later package/control investigation.

```bash
export COMPARE=reference PAIRS=10 TRIAL_SCOPE=library
unset COMPARE_EXECUTABLE
taskset -c "$CPUSET" python3 "$TRIAL_ROOT/bench/paired.py" \
  lapack "$TRIAL_ROOT/bench/lapack-fixed" lu-128 128 50
taskset -c "$CPUSET" python3 "$TRIAL_ROOT/bench/paired.py" \
  lapack "$TRIAL_ROOT/bench/lapack-fixed" lu-1024 1024 3
for p in full reference; do
    sha256sum --check "$TRIAL_ROOT/logs/blas/$p/library.sha256"
done
```

Build missing listed-set variants such as `minus-stack`, `minus-relro`, or `minus-now`; repeat with the same matrix size/repeats and the selected `COMPARE`. `stack-all` is an optional stronger-stack comparison; `minus-clash`, `minus-cf`, and `stack-strong` belong to the extended experiment. Check each `loaded-*.txt` result for the fixed BLAS as well as the intended LAPACK. Because much of the factorization runs in BLAS, a small change here means a small change in this LAPACK-only rebuild scope; it does not establish that rebuilding BLAS with hardening has no cost.

[11](11-stack-comparison.md) compares the whole numerical closure using these matching BLAS/LAPACK builds. The manual commands above use the default library-only scope, retaining full BLAS. To evaluate a vendor BLAS deployment, first select one approved provider and keep it fixed. QR/eigensolver timing and CBLAS/LAPACKE consumer timing are additional workloads; do not generalize this LU result to them without running them.

For PIE, compile this caller with `minus-pie` and keep full LAPACK plus the fixed BLAS loaded. Compare whole-process timing separately. Bounds checking and floating-point exception traps belong in separate diagnostic builds, not in the production-profile runtime comparison.
