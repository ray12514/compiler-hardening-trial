# 05 — Parallel FFTW and HDF5 using matching Open MPI + UCX

**Normal route:** follow the [README](README.md), then run `"$TRIAL_ROOT/runner/trial" build fftw --mpi`. The driver runs the applicable blocks below in child shells, including prerequisites. These numbered sections are recipe references; do not paste all of them after using the driver.

Prerequisites: [00 — GCC](00-gcc-bootstrap.md), [01 — profiles/harness](01-common.md), and [00b — Open MPI + UCX](00b-openmpi-ucx.md). These are separate `fftw-mpi` and `hdf5-mpi` matrices. They use GCC 12.5.0 through qualified Open MPI 4.1.8 wrappers, with matching full/reference UCX 1.16.0 installations. The primary stack comparison changes both payload and dependencies; package-only follow-ups hold full MPI/UCX fixed. LAPACK remains a serial library; MPI consumers can be tested separately.

Build in an allocation sized for compilation and correctness tests. One node is sufficient for builds and local upstream checks, provided it has enough allocated CPU slots for their MPI ranks (the HDF5 recipe allows two). Do not enable oversubscription to hide a slot shortage. The later two-node qualification/pilot establishes inter-node behavior; a one-node build check cannot do that. [08](08-slurm-campaign.md) supplies the planned 1/2/4/8-node campaign and optional denser rank placement. `mpirun` is launched by the paired harness; do not wrap the harness with one-CPU `taskset` for multi-rank jobs. Open MPI performs the recorded rank binding. Regenerate/recompile these callers and the placement header from 00b before using the campaign's placement checks.

```bash
source "$TRIAL_ROOT/env.sh"
source "$TRIAL_ROOT/profiles.sh"
source "$TRIAL_ROOT/mpi-env.sh"
export MPI_NP=2 MPI_MAP=ppr:1:node
export COMPARE=reference PAIRS=10
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
unset UCX_LOG_LEVEL
```

## 1. Build parallel FFTW variants

```bash
FFTW_MPI_VARIANTS=(full reference)
for p in "${FFTW_MPI_VARIANTS[@]}"; do
    activate_mpi_profile "$p"
    profile_flags "$p"
    autotools_flags "$p"
    build="$TRIAL_ROOT/build/fftw-mpi-$p"
    prefix="$TRIAL_ROOT/install/fftw-mpi/$p"
    test ! -e "$build"
    test ! -e "$prefix"
    mkdir -p "$build" "$TRIAL_ROOT/logs/fftw-mpi/$p"
    declare -p AUTOTOOLS_CFLAGS AUTOTOOLS_LDFLAGS MPI_PREFIX UCX_PREFIX > "$TRIAL_ROOT/logs/fftw-mpi/$p/flags.txt"
    (
      cd "$build"
      CC="$CC" MPICC="$MPI_PREFIX/bin/mpicc" CFLAGS="$AUTOTOOLS_CFLAGS" CPPFLAGS='' \
        LDFLAGS="$AUTOTOOLS_LDFLAGS -Wl,-rpath,$MPI_PREFIX/lib" \
        "$TRIAL_ROOT/src/fftw-3.3.11/configure" --prefix="$prefix" \
        --enable-shared --disable-static --enable-threads --enable-sse2 \
        --enable-mpi --disable-fortran \
        2>&1 | tee "$TRIAL_ROOT/logs/fftw-mpi/$p/configure.log"
      make -j "$JOBS" V=1 2>&1 | tee "$TRIAL_ROOT/logs/fftw-mpi/$p/build.log"
      make check 2>&1 | tee "$TRIAL_ROOT/logs/fftw-mpi/$p/check.log"
      make install 2>&1 | tee "$TRIAL_ROOT/logs/fftw-mpi/$p/install.log"
      cp config.log "$TRIAL_ROOT/logs/fftw-mpi/$p/config.log"
    )
    test -f "$prefix/lib/libfftw3_mpi.so"
    readelf -dW "$prefix/lib/libfftw3_mpi.so" > "$TRIAL_ROOT/logs/fftw-mpi/$p/elf.txt"
done
```

Inspect what `make check` actually executes: a serial-only test log does not establish two-node MPI correctness. The following caller supplies a distributed round-trip check on every timed invocation. FFTW's [MPI interface](https://www.fftw.org/doc/MPI-Interface.html) and [data distribution](https://www.fftw.org/doc/MPI-Data-Distribution.html) describe the local slab sizes used here.

### Fixed distributed FFT caller

The caller times collective plan construction and repeated execution, reporting the maximum rank duration. Each run uses a cubic complex transform with the same global size and slab distribution. The inverse check occurs outside execution timing. Thread count is one per rank.

```bash
cat > "$TRIAL_ROOT/bench/fftw_mpi_bench.c" <<'C'
#include <fftw3-mpi.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "mpi_placement.h"
static void fail(void) { MPI_Abort(MPI_COMM_WORLD,1); exit(1); }
int main(int argc,char **argv) {
    MPI_Init(&argc,&argv);
    trial_mpi_placement();
    int rank; MPI_Comm_rank(MPI_COMM_WORLD,&rank);
    if(argc!=4) fail();
    ptrdiff_t n=(ptrdiff_t)atoll(argv[1]); int reps=atoi(argv[2]);
    if(n<2 || n>256 || reps<1) fail();
    unsigned flags;
    if(!strcmp(argv[3],"estimate")) flags=FFTW_ESTIMATE;
    else if(!strcmp(argv[3],"measure")) flags=FFTW_MEASURE;
    else fail();
    fftw_mpi_init();
    ptrdiff_t local0,start;
    ptrdiff_t allocated=fftw_mpi_local_size_3d(n,n,n,MPI_COMM_WORLD,&local0,&start);
    if(local0<1) fail();
    fftw_complex *in=fftw_alloc_complex(allocated), *out=fftw_alloc_complex(allocated);
    fftw_complex *back=fftw_alloc_complex(allocated);
    if(!in || !out || !back) fail();
    for(ptrdiff_t i=0;i<allocated;i++) { in[i][0]=0; in[i][1]=0; }
    MPI_Barrier(MPI_COMM_WORLD); double t=MPI_Wtime();
    fftw_plan f=fftw_mpi_plan_dft_3d(n,n,n,in,out,MPI_COMM_WORLD,FFTW_FORWARD,flags);
    double plan_local=MPI_Wtime()-t, planning;
    MPI_Allreduce(&plan_local,&planning,1,MPI_DOUBLE,MPI_MAX,MPI_COMM_WORLD);
    fftw_plan b=fftw_mpi_plan_dft_3d(n,n,n,out,back,MPI_COMM_WORLD,FFTW_BACKWARD,FFTW_ESTIMATE);
    if(!f || !b) fail();
    ptrdiff_t count=local0*n*n; double total=(double)n*n*n;
    for(ptrdiff_t i=0;i<count;i++) {
        double index=(double)(start*n*n+i);
        in[i][0]=sin(0.1*index); in[i][1]=cos(0.03*index);
    }
    fftw_execute(f); fftw_execute(b);
    double error_local=0,error;
    for(ptrdiff_t i=0;i<count;i++) for(int j=0;j<2;j++) {
        double e=fabs(back[i][j]/total-in[i][j]);
        if(!isfinite(e)) fail();
        if(e>error_local) error_local=e;
    }
    MPI_Allreduce(&error_local,&error,1,MPI_DOUBLE,MPI_MAX,MPI_COMM_WORLD);
    if(error>1e-8) fail();
    MPI_Barrier(MPI_COMM_WORLD); t=MPI_Wtime();
    for(int r=0;r<reps;r++) fftw_execute(f);
    double execution_local=MPI_Wtime()-t,execution;
    MPI_Allreduce(&execution_local,&execution,1,MPI_DOUBLE,MPI_MAX,MPI_COMM_WORLD);
    if(rank==0) printf("planning_maxrank,%.17g,%.17g\nexecution_maxrank,%.17g,%.17g\n",planning,error,execution,error);
    fftw_destroy_plan(f); fftw_destroy_plan(b);
    fftw_free(in); fftw_free(out); fftw_free(back); fftw_mpi_cleanup();
    MPI_Finalize(); return 0;
}
C
activate_mpi_profile full
profile_flags full
read -r -a cargs <<< "$EXE_CFLAGS"
read -r -a largs <<< "$EXE_LDFLAGS"
"$MPI_PREFIX/bin/mpicc" "${cargs[@]}" \
  -I "$TRIAL_ROOT/install/fftw-mpi/full/include" "$TRIAL_ROOT/bench/fftw_mpi_bench.c" \
  -L "$TRIAL_ROOT/install/fftw-mpi/full/lib" -lfftw3_mpi -lfftw3 -lm \
  -Wl,--enable-new-dtags -Wl,-rpath,"$TRIAL_ROOT/install/fftw-mpi/full/lib" \
  "${largs[@]}" -o "$TRIAL_ROOT/bench/fftw-mpi-fixed"
```

#### Optional FFTW package-only timings

Complete 11/08's stack comparison first. These fixed-caller timings retain full MPI/UCX for later package attribution.

```bash
export TRIAL_SCOPE=library
unset COMPARE_EXECUTABLE
python3 "$TRIAL_ROOT/bench/paired.py" \
  fftw-mpi "$TRIAL_ROOT/bench/fftw-mpi-fixed" 2ranks-32cube-estimate 32 200  estimate
python3 "$TRIAL_ROOT/bench/paired.py" \
  fftw-mpi "$TRIAL_ROOT/bench/fftw-mpi-fixed" 2ranks-64cube-estimate 64 100 estimate
python3 "$TRIAL_ROOT/bench/paired.py" \
  fftw-mpi "$TRIAL_ROOT/bench/fftw-mpi-fixed" 2ranks-64cube-measure 64 100 measure
```

Planning and communication can mask local arithmetic overhead; retain the serial results too. Increase counts for short execution phases. Build removal variants using section 1 and select `COMPARE=minus-stack`, etc., with the same ranks, mapping, transform, planner, and repetition count.

## 2. Build parallel HDF5 variants

C-only, compression/plugin/thread-safe options off, high-level library and parallel tools on. Set MPI discovery explicitly; do not let CMake discover a system MPI ahead of the private one. Tests below run sequentially because MPI test jobs must fit the allocation; they still launch multiple ranks.

```bash
HDF5_MPI_VARIANTS=(full reference)
for p in "${HDF5_MPI_VARIANTS[@]}"; do
    activate_mpi_profile "$p"
    profile_flags "$p"
    build="$TRIAL_ROOT/build/hdf5-mpi-$p"
    prefix="$TRIAL_ROOT/install/hdf5-mpi/$p"
    test ! -e "$build"
    test ! -e "$prefix"
    mkdir -p "$TRIAL_ROOT/logs/hdf5-mpi/$p"
    "$CMAKE" -S "$TRIAL_ROOT/src/hdf5-2.1.0" -B "$build" -G 'Unix Makefiles' \
      -DCMAKE_C_COMPILER="$MPI_PREFIX/bin/mpicc" -DMPI_C_COMPILER="$MPI_PREFIX/bin/mpicc" \
      -DMPIEXEC_EXECUTABLE="$MPI_PREFIX/bin/mpirun" -DMPIEXEC_MAX_NUMPROCS=2 \
      -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_FLAGS="$CFLAGS" -DCMAKE_C_FLAGS_RELEASE='' \
      -DCMAKE_SHARED_LINKER_FLAGS="$SHARED_LDFLAGS" \
      -DCMAKE_EXE_LINKER_FLAGS="$EXE_LDFLAGS" \
      -DCMAKE_INSTALL_PREFIX="$prefix" -DCMAKE_INSTALL_LIBDIR=lib \
      -DCMAKE_INSTALL_RPATH="$MPI_PREFIX/lib" -DCMAKE_EXPORT_COMPILE_COMMANDS=ON \
      -DBUILD_SHARED_LIBS=ON -DBUILD_STATIC_LIBS=OFF -DBUILD_TESTING=ON \
      -DHDF5_BUILD_TOOLS=ON -DHDF5_BUILD_PARALLEL_TOOLS=ON -DHDF5_BUILD_HL_LIB=ON \
      -DHDF5_BUILD_CPP_LIB=OFF -DHDF5_BUILD_FORTRAN=OFF \
      -DHDF5_ENABLE_PARALLEL=ON -DHDF5_ENABLE_THREADSAFE=OFF \
      -DHDF5_ENABLE_ZLIB_SUPPORT=OFF -DHDF5_ENABLE_SZIP_SUPPORT=OFF \
      -DHDF5_ENABLE_PLUGIN_SUPPORT=OFF -DHDF5_ENABLE_NONSTANDARD_FEATURE_FLOAT16=OFF \
      2>&1 | tee "$TRIAL_ROOT/logs/hdf5-mpi/$p/configure.log"
    "$CMAKE" --build "$build" --parallel "$JOBS" --verbose \
      2>&1 | tee "$TRIAL_ROOT/logs/hdf5-mpi/$p/build.log"
    "$CTEST" --test-dir "$build" --output-on-failure --parallel 1 \
      2>&1 | tee "$TRIAL_ROOT/logs/hdf5-mpi/$p/check.log"
    "$CMAKE" --install "$build" 2>&1 | tee "$TRIAL_ROOT/logs/hdf5-mpi/$p/install.log"
    cp "$build/CMakeCache.txt" "$build/compile_commands.json" "$TRIAL_ROOT/logs/hdf5-mpi/$p/"
    test -f "$prefix/lib/libhdf5.so"
    ldd "$prefix/lib/libhdf5.so" > "$TRIAL_ROOT/logs/hdf5-mpi/$p/loaded.txt"
done
```

Review `ctest -N -V` before running to confirm rank counts fit the actual allocation and that MPI tests were generated. If a test needs more ranks than allocated, request the required allocation rather than enabling oversubscription or skipping a failure. The recorded MPI compiler/libs must belong to `MPI_PREFIX`.

### Fixed parallel I/O caller

Each rank writes a disjoint slab into one shared file, then reads and verifies its own slab. Metadata creation is collective in both modes; dataset transfer uses the selected independent or collective mode. It reports maximum-rank write/read duration. The dataset is contiguous and uncompressed. Reading follows writing and is warm-cache; close completion is not a claim of physical-media durability.

The filename must be dedicated to this trial and visible at the same path from both nodes. Node-local `/tmp` is not a shared-filesystem substitute for this workload. See [parallel HDF5 overview](https://support.hdfgroup.org/documentation/hdf5-docs/hdf5_topics/ParallelHDF5.html).

```bash
cat > "$TRIAL_ROOT/bench/hdf5_mpi_bench.c" <<'C'
#include <mpi.h>
#include <hdf5.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include "mpi_placement.h"
static void fail(void) { MPI_Abort(MPI_COMM_WORLD,1); exit(1); }
#define CHECK(x) do { if((x)<0) { fprintf(stderr,"HDF5 failure: %s\n",#x); fail(); } } while(0)
int main(int argc,char **argv) {
    MPI_Init(&argc,&argv);
    trial_mpi_placement();
    int rank,size; MPI_Comm_rank(MPI_COMM_WORLD,&rank); MPI_Comm_size(MPI_COMM_WORLD,&size);
    if(argc!=4) fail();
    size_t n=(size_t)strtoull(argv[2],0,10);
    if(n<1 || n>33554432) fail();
    int collective=!strcmp(argv[3],"collective");
    if(!collective && strcmp(argv[3],"independent")) fail();
    double *in=malloc(n*sizeof *in), *out=malloc(n*sizeof *out);
    if(!in || !out) fail();
    for(size_t i=0;i<n;i++) in[i]=rank+1.0+(i%1024)*0.001;
    hsize_t global[1]={(hsize_t)n*size}, local[1]={(hsize_t)n}, start[1]={(hsize_t)n*rank};
    hid_t fapl=H5Pcreate(H5P_FILE_ACCESS); CHECK(fapl);
    CHECK(H5Pset_fapl_mpio(fapl,MPI_COMM_WORLD,MPI_INFO_NULL));
    hid_t dxpl=H5Pcreate(H5P_DATASET_XFER); CHECK(dxpl);
    CHECK(H5Pset_dxpl_mpio(dxpl,collective ? H5FD_MPIO_COLLECTIVE : H5FD_MPIO_INDEPENDENT));
    hid_t mem=H5Screate_simple(1,local,0); CHECK(mem);
    MPI_Barrier(MPI_COMM_WORLD); double t=MPI_Wtime();
    hid_t f=H5Fcreate(argv[1],H5F_ACC_TRUNC,H5P_DEFAULT,fapl); CHECK(f);
    hid_t space=H5Screate_simple(1,global,0); CHECK(space);
    hid_t d=H5Dcreate2(f,"data",H5T_IEEE_F64LE,space,H5P_DEFAULT,H5P_DEFAULT,H5P_DEFAULT); CHECK(d);
    CHECK(H5Sselect_hyperslab(space,H5S_SELECT_SET,start,0,local,0));
    CHECK(H5Dwrite(d,H5T_NATIVE_DOUBLE,mem,space,dxpl,in));
    CHECK(H5Dclose(d)); CHECK(H5Sclose(space)); CHECK(H5Fclose(f));
    double write_local=MPI_Wtime()-t,writing;
    MPI_Allreduce(&write_local,&writing,1,MPI_DOUBLE,MPI_MAX,MPI_COMM_WORLD);
    MPI_Barrier(MPI_COMM_WORLD); t=MPI_Wtime();
    f=H5Fopen(argv[1],H5F_ACC_RDONLY,fapl); CHECK(f);
    d=H5Dopen2(f,"data",H5P_DEFAULT); CHECK(d);
    space=H5Dget_space(d); CHECK(space);
    CHECK(H5Sselect_hyperslab(space,H5S_SELECT_SET,start,0,local,0));
    CHECK(H5Dread(d,H5T_NATIVE_DOUBLE,mem,space,dxpl,out));
    CHECK(H5Dclose(d)); CHECK(H5Sclose(space)); CHECK(H5Fclose(f));
    double read_local=MPI_Wtime()-t,reading;
    MPI_Allreduce(&read_local,&reading,1,MPI_DOUBLE,MPI_MAX,MPI_COMM_WORLD);
    double error_local=0,error;
    for(size_t i=0;i<n;i++) {
        if(!isfinite(out[i])) fail();
        double e=fabs(out[i]-in[i]); if(e>error_local) error_local=e;
    }
    MPI_Allreduce(&error_local,&error,1,MPI_DOUBLE,MPI_MAX,MPI_COMM_WORLD);
    if(error>1e-12) fail();
    CHECK(H5Sclose(mem)); CHECK(H5Pclose(dxpl)); CHECK(H5Pclose(fapl));
    MPI_Barrier(MPI_COMM_WORLD);
    if(rank==0) {
        printf("write_%s_maxrank,%.17g,%.17g\nread_%s_warm_maxrank,%.17g,%.17g\n",argv[3],writing,error,argv[3],reading,error);
        if(unlink(argv[1])<0) fail();
    }
    free(in); free(out); MPI_Finalize(); return 0;
}
C
activate_mpi_profile full
profile_flags full
read -r -a cargs <<< "$EXE_CFLAGS"
read -r -a largs <<< "$EXE_LDFLAGS"
"$MPI_PREFIX/bin/mpicc" "${cargs[@]}" -I "$TRIAL_ROOT/install/hdf5-mpi/full/include" \
  "$TRIAL_ROOT/bench/hdf5_mpi_bench.c" -L "$TRIAL_ROOT/install/hdf5-mpi/full/lib" \
  -Wl,--enable-new-dtags -Wl,-rpath,"$TRIAL_ROOT/install/hdf5-mpi/full/lib" \
  -lhdf5 -lm "${largs[@]}" -o "$TRIAL_ROOT/bench/hdf5-mpi-fixed"
```

#### Optional HDF5 package-only timings

Complete 11/08's stack comparison first. These fixed-caller timings retain full MPI/UCX for later package attribution.

```bash
export TRIAL_SCOPE=library
unset COMPARE_EXECUTABLE
export IO_DIR=/absolute/path/to/shared-test-filesystem/hdf5-hardening-trial
mkdir -p "$IO_DIR"
python3 "$TRIAL_ROOT/bench/paired.py" \
  hdf5-mpi "$TRIAL_ROOT/bench/hdf5-mpi-fixed" 2ranks-128MiB-collective \
  "$IO_DIR/hdf5-mpi-trial.h5" 8388608 collective
python3 "$TRIAL_ROOT/bench/paired.py" \
  hdf5-mpi "$TRIAL_ROOT/bench/hdf5-mpi-fixed" 2ranks-128MiB-independent \
  "$IO_DIR/hdf5-mpi-trial.h5" 8388608 independent
```

For two ranks this is 64 MiB per rank, 128 MiB total. Increasing ranks with the same per-rank element count is a weak-scaling change; holding global data size fixed is a different scaling experiment. Label both properly. This caller measures transfer-mode requests; recording HDF5's actual-I/O-mode diagnostics is useful before attributing collective optimization behavior to the request alone.

Build missing removal variants with the same section 2 flags, select each `COMPARE`, and repeat identical workloads. Record filesystem, Open MPI ROMIO component, UCX transports/devices, mapping, ranks, and loaded dependency paths. Serial and parallel comparisons answer different questions and should remain separate.

## Return to serial comparisons

```bash
unset MPI_NP MPI_MAP MPI_EXTRA_ARGS
```

The paired harness uses a launcher only when `MPI_NP` is set to a positive count. Reset it before returning to serial FFTW, serial HDF5, or LAPACK timings.
