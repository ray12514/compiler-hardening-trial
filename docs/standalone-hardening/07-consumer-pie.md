# 07 Executable PIE comparison

Prerequisites: 00–04 and the setup sections of 06. Use the listed profile from 01 by default. The package library tests hold a fully hardened caller fixed, so they do not attribute PIE overhead. This procedure builds a second caller with PIE disabled while holding the full libraries, stack protector, FORTIFY, RELRO, and NOW fixed. It measures whole-process elapsed time, including startup, workload, validation, and exit.

FFTW/HDF5/LAPACK shared libraries retain `-fPIC` in every arm. `-fPIE` and `-pie` apply to the caller executables. For LAPACK, the fixed reference BLAS also remains unchanged.

## 1. Build the three non-PIE callers

Run in Bash. The source files and full callers were created in 02–04. All link flags below are passed through the GCC/GFortran driver. `minus-pie` changes only executable position independence relative to `full`.

```bash
source "$TRIAL_ROOT/env.sh"
source "$TRIAL_ROOT/profiles.sh"
export BLAS_PREFIX="$TRIAL_ROOT/install/blas/full"
profile_flags minus-pie
read -r -a cargs <<< "$EXE_CFLAGS"
read -r -a fargs <<< "$EXE_FFLAGS"
read -r -a largs <<< "$EXE_LDFLAGS"
for package in fftw hdf5 lapack; do
    test -x "$TRIAL_ROOT/bench/$package-fixed"
    test ! -e "$TRIAL_ROOT/bench/$package-minus-pie"
done
mkdir -p "$TRIAL_ROOT/logs/consumer-pie"
declare -p EXE_CFLAGS EXE_FFLAGS EXE_LDFLAGS \
  > "$TRIAL_ROOT/logs/consumer-pie/minus-pie-flags.txt"
"$CC" "${cargs[@]}" -I "$TRIAL_ROOT/install/fftw/full/include" \
  "$TRIAL_ROOT/bench/fftw_bench.c" -L "$TRIAL_ROOT/install/fftw/full/lib" \
  -Wl,--enable-new-dtags -Wl,-rpath,"$TRIAL_ROOT/install/fftw/full/lib" \
  -lfftw3_threads -lfftw3 -lm -pthread "${largs[@]}" \
  -o "$TRIAL_ROOT/bench/fftw-minus-pie"
"$CC" "${cargs[@]}" -I "$TRIAL_ROOT/install/hdf5/full/include" \
  "$TRIAL_ROOT/bench/hdf5_bench.c" -L "$TRIAL_ROOT/install/hdf5/full/lib" \
  -Wl,--enable-new-dtags -Wl,-rpath,"$TRIAL_ROOT/install/hdf5/full/lib" \
  -lhdf5 -lm "${largs[@]}" -o "$TRIAL_ROOT/bench/hdf5-minus-pie"
"$FC" "${fargs[@]}" "$TRIAL_ROOT/bench/lapack_bench.f90" \
  -L "$TRIAL_ROOT/install/lapack/full/lib" -llapack \
  -L "$BLAS_PREFIX/lib" -lblas -Wl,--enable-new-dtags \
  -Wl,-rpath,"$TRIAL_ROOT/install/lapack/full/lib" -Wl,-rpath,"$BLAS_PREFIX/lib" \
  "${largs[@]}" -o "$TRIAL_ROOT/bench/lapack-minus-pie"
for package in fftw hdf5 lapack; do
    for arm in fixed minus-pie; do
        readelf -hW "$TRIAL_ROOT/bench/$package-$arm" \
          > "$TRIAL_ROOT/logs/consumer-pie/$package-$arm-elf.txt"
        readelf -lW "$TRIAL_ROOT/bench/$package-$arm" \
          >> "$TRIAL_ROOT/logs/consumer-pie/$package-$arm-elf.txt"
        readelf -dW "$TRIAL_ROOT/bench/$package-$arm" \
          >> "$TRIAL_ROOT/logs/consumer-pie/$package-$arm-elf.txt"
    done
done
```

Verify `*-fixed` is ELF `DYN` with PIE executable semantics and `*-minus-pie` is `EXEC`. Both should have GNU_RELRO and NOW/BIND_NOW, and a non-executable stack. An ELF `DYN` type alone does not distinguish a shared library from a PIE executable; inspect the interpreter and PIE flag as appropriate. Compare loaded-library records and retain flag/ELF evidence with results.

## 2. Run the paired caller comparison with ReFrame

Use an allocated CPU and a dedicated I/O directory. HDF5 reads remain warm-cache, and buffered close is not a physical-storage durability measurement. Use the same inputs and repeat counts for both callers.

```bash
export CPUSET=0  # replace with an allocated CPU
export IO_DIR=/absolute/path/to/test-filesystem/hdf5-hardening-trial
mkdir -p "$IO_DIR"
export WORKLOADS=fft-pie,hdf5-pie,lapack-pie
export COMPARATORS=minus-pie PAIRS=10
export RUN_ID
RUN_ID=$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$TRIAL_ROOT/results/reframe/$RUN_ID"
REFRAME="$TRIAL_ROOT/tools/reframe-venv/bin/reframe"
"$REFRAME" -C "$TRIAL_ROOT/reframe/settings.py" \
  -c "$TRIAL_ROOT/reframe/hardening.py" -r --exec-policy=serial \
  --performance-report --prefix="$TRIAL_ROOT/results/reframe/$RUN_ID/rfm" \
  --report-file="$TRIAL_ROOT/results/reframe/$RUN_ID/report.json" \
  2>&1 | tee "$TRIAL_ROOT/results/reframe/$RUN_ID/console.log"
```

The primary phase is `process_elapsed`. Positive runtime change means the PIE caller took longer than the non-PIE caller. The harness verifies that **both arms load the full package libraries**, records both caller paths, and labels the summary `scope=consumer-pie`. Kernel phase timings remain in the raw CSV and summary but cannot be substituted for the whole-process PIE comparison.

The wall-clock measurement includes process-launch and output-capture costs; it is not an isolated loader microbenchmark. Use enough pairs and inspect variability. These cases use short workloads (HDF5 contains 128 doubles) to make startup effects more visible. A larger deployment workload can mask a small startup effect and needs a separately labelled comparison.

Return to `COMPARATORS=reference` and ordinary workload names for library comparisons. ReFrame sets the caller override only for the PIE workloads. For manual use of `paired.py`, set `COMPARE=minus-pie` and `COMPARE_EXECUTABLE` to the corresponding `*-minus-pie` path; unset `COMPARE_EXECUTABLE` before returning to library tests.
