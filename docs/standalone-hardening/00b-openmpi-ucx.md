# 00b — Open MPI 4.1.8 with UCX 1.16.0 and GCC 12.5.0

**Normal route:** follow the [README](README.md), run `"$TRIAL_ROOT/runner/trial" prepare-mpi` on the login node, then `"$TRIAL_ROOT/runner/trial" build fftw --mpi` on the compute node. The driver runs the applicable blocks below in child shells, including prerequisites. These numbered sections are recipe references; do not paste all of them after using the driver.

Run after [00 — GCC bootstrap](00-gcc-bootstrap.md) and [01 — profile qualification](01-common.md), before the MPI FFTW/HDF5 builds. These versions are fixed inputs to this experiment. Build the complete `full` stack first, then its matched `reference` stack. [11](11-stack-comparison.md) selects matching MPI/UCX and payload arms for the primary comparison. Later package-only investigations hold the full MPI/UCX stack fixed.

## Where profiles.sh comes from and what to run next

`env.sh` is created by the GCC bootstrap in 00. **`profiles.sh` is created separately in [01, section 1](01-common.md#1-create-explicit-profiles)** by its `cat > "$TRIAL_ROOT/profiles.sh"` block. If GCC is already installed but that file is missing, run 01 section 1 and [section 2, compiler-flag qualification](01-common.md#2-qualify-flags-before-expensive-builds), then return here. There is no GCC rebuild for this step. Use the order **00 -> 01 -> 00b -> package builds**; the `00b` filename does not mean it precedes 01.

The common setup defines full/reference/removal flag profiles, compiles small qualification probes with the existing GCC, and creates the paired-measurement helper used later. It does not rebuild GCC, change GCC's defaults/specs, or enable a compiler profiler. Calling `profile_flags full` selects variables passed to the subsequent package configure/build commands. Here, UCX and Open MPI are built with matching full/reference profiles. The full installation remains fixed only for the later package-only comparisons. The executable PIE settings are separate from shared-library PIC settings.

After generating the file, confirm it loads in the build shell:

```bash
source "$TRIAL_ROOT/env.sh"
test -f "$TRIAL_ROOT/profiles.sh" || {
    printf '%s\n' 'Create profiles.sh using 01-common section 1, then qualify the flags in section 2.' >&2
    exit 1
}
source "$TRIAL_ROOT/profiles.sh"
type profile_flags
profile_flags full
printf 'CFLAGS=%s\nShared-library LDFLAGS=%s\n' "$CFLAGS" "$SHARED_LDFLAGS"
```

## System and trial components

| Component | This procedure uses |
|---|---|
| GCC/binutils | Private installations created by 00 |
| Open MPI 4.1.8 | Private source build using the private GCC C/C++/Fortran drivers |
| UCX 1.16.0 | Private source build; Open MPI receives its exact prefix through `--with-ucx` |
| Slurm | Existing site clients, allocation, configuration, and daemons; no Slurm source build or update |
| PMIx, hwloc, libevent | Open MPI's bundled copies; site versions are not selected |
| libc, development files, fabric drivers and optional verbs/rdmacm | Existing approved OS/site prerequisites; no package installation or driver changes |

Keep these versions fixed for matched comparisons. This standalone recipe uses `mpirun` inside the site's Slurm allocation. Direct `srun --mpi=...` application launch with a site PMI/PMIx library requires separate site integration and qualification. [Open MPI v4 Slurm integration](https://www.open-mpi.org/faq/?category=slurm)

Follow [the environment procedure](00-build-environment.md) to retain required master modules while removing inherited AOCC/MPI paths and overrides. Rebuild from fresh directories when changing the environment; existing configure/CMake caches can retain old dependency paths.

## 1. Stage exact MPI sources

**This is a login/staging-node preparation step, before the compute-node build.** The normal command is `trial prepare-mpi`; it downloads and verifies both archives without requiring profile qualification. `trial prepare-mpi --from-dir DIR` imports transferred archives, and `trial prepare-mpi --check` verifies the local cache without network access. Build commands only extract verified local archives; they do not invoke the download block below.

Use Open MPI's official release archive, not GitHub's automatically generated source snapshot. The following manual recipe records the canonical filenames, URLs and checksums used by the driver. Run its downloads only on a host allowed to connect, then stage/transfer the archives into the trial's `downloads/` directory. For download-only staging before profiles exist, use `prepare-mpi` or the two curl commands with the checksum list; the full manual block assumes the common setup is already present.

```bash
source "$TRIAL_ROOT/env.sh"
source "$TRIAL_ROOT/profiles.sh"
cd "$TRIAL_ROOT/downloads"
curl -fL --retry 3 -o openmpi-4.1.8.tar.bz2 \
  https://download.open-mpi.org/release/open-mpi/v4.1/openmpi-4.1.8.tar.bz2
curl -fL --retry 3 -o ucx-1.16.0.tar.gz \
  https://github.com/openucx/ucx/releases/download/v1.16.0/ucx-1.16.0.tar.gz
cat > MPI-SHA256SUMS <<'SUMS'
466f68e3132a1dc02710cc2011fafced8336d98359fa2dae4dddcfd5719f12a9  openmpi-4.1.8.tar.bz2
f73770d3b583c91aba5fb07557e655ead0786e057018bfe42f0ebe8716e9d28c  ucx-1.16.0.tar.gz
SUMS
sha256sum --check MPI-SHA256SUMS | tee "$TRIAL_ROOT/logs/mpi-sources.log"
tar -xf ucx-1.16.0.tar.gz -C "$TRIAL_ROOT/src"
tar -xf openmpi-4.1.8.tar.bz2 -C "$TRIAL_ROOT/src"
export UCX_PREFIX="$TRIAL_ROOT/install/ucx-1.16.0-fixed"
export MPI_PREFIX="$TRIAL_ROOT/install/openmpi-4.1.8-ucx-fixed"
MPI_VARIANTS=(full reference)  # select only missing entries if full is already qualified
```

Source references: [Open MPI 4.1 downloads](https://www.open-mpi.org/software/ompi/v4.1/), [UCX build and Open MPI integration](https://openucx.readthedocs.io/en/master/running.html).

## 2. Select the UCX transport prerequisites

UCX can run over TCP/shared memory without RDMA development libraries. For an InfiniBand/RoCE trial, the site must supply compatible verbs/rdmacm headers and libraries, kernel drivers, and access to the relevant devices. Building UCX alone does not install network drivers. Record `ucx_info -d` on the compute nodes; do not describe a TCP fallback as RDMA performance.

Choose exactly one array below. The default is a portable TCP/shared-memory bring-up. If the trial is intended to exercise RDMA, select the RDMA array before building and fail if its prerequisites cannot be found.

**For driver-managed Mellanox/RDMA builds**, set
`export TRIAL_UCX_CONFIGURE_ARGS='--with-verbs --with-rdmacm'`
before the first UCX arm is built.

The driver otherwise uses `--without-verbs --without-rdmacm`. The manual array
below does not change that driver setting. Site-specific prefixes may be needed
for compatible development headers/libraries. Inspect both arms' `flags.txt`,
`configure.log` and `ucx_info -v/-d`; hardware being present does not prove UCX
was compiled with access to it. A UCX build without verbs cannot acquire RDMA
support through `UCX_TLS` or `mpirun` options afterward.

Changing this setting changes the recorded UCX build inputs and dependent MPI
stack. Do not use `--retry` to relabel completed TCP builds as RDMA builds or
delete completion records. Preserve the current trial and choose an explicit
rebuild plan after inspecting the completed/pending state. Failed, incomplete
driver attempts use the existing retry procedure.

```bash
UCX_TRANSPORT_ARGS=(--without-verbs --without-rdmacm)
# For an IB/RoCE system with development libraries installed, use instead:
# UCX_TRANSPORT_ARGS=(--with-verbs --with-rdmacm)
# For libraries in a nonstandard site prefix, use --with-verbs=/prefix and
# --with-rdmacm=/prefix, and preserve their runtime paths on every node.
```

Leave UCX's runtime transport selection at its normal defaults initially. Record any later `UCX_TLS`/`UCX_NET_DEVICES` choices and apply them identically to both arms. A non-IB fabric requires its own supported UCX configuration; verify available transports rather than guessing from the machine's vendor name.

For a CPU-only RDMA pilot, an explicitly qualified allow-list such as
`UCX_TLS=rc,sm,self` retains shared memory within nodes and RC/its bootstrap
transports between nodes while excluding UCX TCP payload transport. `--mca pml
ucx` alone does not establish which UCX transport carried the data. Launcher and
scheduler control traffic can still use TCP.

Use `ucx_info -d` on the allocated compute nodes, plus available site tools such
as `ibv_devinfo`/`ibstat`, to identify usable device/port pairs. UCX names look
like `mlx5_0:1`, but that is an example, not a portable setting. Device presence
does not establish an active, mutually reachable port. Leave device selection
automatic until qualified, or select ports verified on every selected host.
InfiniBand and RoCE may require different site settings; do not guess a GID
index, service level or device name. See [UCX network selection](https://openucx.readthedocs.io/en/master/faq.html#selecting-networks-and-transports).

The activation scripts clear inherited UCX settings. Apply qualified tuning
after each MPI environment activation. Campaign 08/10 supports a recorded
`TRIAL_MPI_TUNING` file; the individual driver pilot and manual smoke must also
be checked for propagation after activation before relying on those settings.
Retain the MPI placement/communication verification: a PML or device-open
failure holds the MPI results until resolved.

The report must identify both arms' UCX configure options and library paths,
device/port capabilities on every host, runtime transport/device settings,
memlock limit, and a successful native multi-node qualification log showing
the selected RDMA path. `UCX_TLS` in a summary records a request, not proof of
the selected network. Keep verbose UCX diagnostics out of timed samples and
retain qualification failures alongside the eventual successful evidence.

## 3. Build matching UCX variants

Build full first, then reference with the same transport choices and configure options. `autotools_flags` from 01 qualifies conditional executable PIE linking while Libtool retains library PIC. Keep its specs files with this immutable trial tree; they do not change GCC defaults. UCX's release configuration disables diagnostic instrumentation unrelated to this production experiment. If that fixed profile causes an MPI/UCX compatibility failure, resolve and record the chosen dependency profile before building any payloads.

```bash
for p in "${MPI_VARIANTS[@]}"; do
mpi_profile_prefixes "$p"
profile_flags "$p"
autotools_flags "$p"
tag=ucx-fixed
if test "$p" = reference; then tag=ucx-reference; fi
build="$TRIAL_ROOT/build/$tag"
test ! -e "$build"
    test ! -e "$UCX_PREFIX"
mkdir -p "$build" "$TRIAL_ROOT/logs/$tag"
(
  cd "$build"
  CC="$CC" CXX="$CXX" CFLAGS="$AUTOTOOLS_CFLAGS" CXXFLAGS="$AUTOTOOLS_CXXFLAGS" \
    CPPFLAGS='' LDFLAGS="$AUTOTOOLS_LDFLAGS" \
    "$TRIAL_ROOT/src/ucx-1.16.0/contrib/configure-release" \
    --prefix="$UCX_PREFIX" --libdir="$UCX_PREFIX/lib" \
    --enable-shared --disable-static --enable-mt \
    --without-cuda --without-rocm --without-java --without-go --without-knem --without-xpmem \
    "${UCX_TRANSPORT_ARGS[@]}" \
    2>&1 | tee "$TRIAL_ROOT/logs/$tag/configure.log"
  make -j "$JOBS" V=1 2>&1 | tee "$TRIAL_ROOT/logs/$tag/build.log"
  make check 2>&1 | tee "$TRIAL_ROOT/logs/$tag/check.log"
  make install 2>&1 | tee "$TRIAL_ROOT/logs/$tag/install.log"
  cp config.log "$TRIAL_ROOT/logs/$tag/config.log"
)
export LD_LIBRARY_PATH="$UCX_PREFIX/lib:$GCC_LIB_DIRS${TRIAL_SITE_LIB_DIRS:+:$TRIAL_SITE_LIB_DIRS}"
"$UCX_PREFIX/bin/ucx_info" -v > "$TRIAL_ROOT/logs/$tag/version.txt"
"$UCX_PREFIX/bin/ucx_info" -d > "$TRIAL_ROOT/logs/$tag/devices.txt"
declare -p AUTOTOOLS_CFLAGS AUTOTOOLS_CXXFLAGS AUTOTOOLS_LDFLAGS UCX_TRANSPORT_ARGS > "$TRIAL_ROOT/logs/$tag/flags.txt"
done
```

Review configure warnings for unrecognized options and confirm threading support and the selected network transports in the built configuration. Testing requirements may vary by installed optional transport; retain failures and resolve them rather than ignoring the test result.

Go bindings are explicitly disabled for both arms. UCX 1.16.0 otherwise guesses
Go support from the available compiler, while the pinned release archive omits
the Go source directories referenced by its binding Makefiles. That combination
fails late in `make` with missing `bindings/go/src/ucx` or
`bindings/go/src/examples/perftest` paths and Go module/source errors. The trial
uses UCX's C library through Open MPI, so these optional bindings are outside
its build scope. See UCX's [Go configure rule](https://github.com/openucx/ucx/blob/v1.16.0/config/m4/go.m4)
and [binding Makefile](https://github.com/openucx/ucx/blob/v1.16.0/bindings/go/Makefile.am).
The configure summary should show an empty `Bindings` list.

## 4. Build matching Open MPI variants against UCX

The example assumes Slurm, as in the existing trial examples. Confirm the recorded `SLURM_BINDIR` contains the existing site's `srun` and `salloc`; preserve `SLURM_*` settings from the allocation and required master modules. `--with-slurm` requests Open MPI's Slurm integration; it does not install Slurm. For another scheduler, replace that configuration before building. Open MPI supplies bundled hwloc, libevent, and PMIx, so their development packages are not assumed present. ROMIO is enabled and selected consistently for the HDF5 MPI-IO phase.

```bash
for p in "${MPI_VARIANTS[@]}"; do
mpi_profile_prefixes "$p"
profile_flags "$p"
autotools_flags "$p"
export LD_LIBRARY_PATH="$UCX_PREFIX/lib:$GCC_LIB_DIRS${TRIAL_SITE_LIB_DIRS:+:$TRIAL_SITE_LIB_DIRS}"
tag=openmpi-fixed
envfile="$TRIAL_ROOT/mpi-env.sh"
if test "$p" = reference; then
    tag=openmpi-reference
    envfile="$TRIAL_ROOT/mpi-env-reference.sh"
fi
build="$TRIAL_ROOT/build/$tag"
test ! -e "$build"
    test ! -e "$MPI_PREFIX"
mkdir -p "$build" "$TRIAL_ROOT/logs/$tag"
(
  cd "$build"
  CC="$CC" CXX="$CXX" FC="$FC" CFLAGS="$AUTOTOOLS_CFLAGS" CXXFLAGS="$AUTOTOOLS_CXXFLAGS" \
    FCFLAGS="$AUTOTOOLS_FFLAGS" FFLAGS="$AUTOTOOLS_FFLAGS" CPPFLAGS='' \
    LDFLAGS="$AUTOTOOLS_LDFLAGS -Wl,-rpath,$UCX_PREFIX/lib" \
    "$TRIAL_ROOT/src/openmpi-4.1.8/configure" \
    --prefix="$MPI_PREFIX" --libdir="$MPI_PREFIX/lib" \
    --with-ucx="$UCX_PREFIX" --with-hwloc=internal --with-libevent=internal \
    --with-pmix=internal --with-slurm --enable-io-romio \
    --enable-mpi-fortran=all --disable-mpi-cxx --disable-oshmem \
    --enable-shared --disable-static --without-cuda \
    --enable-mca-no-build=btl-uct \
    2>&1 | tee "$TRIAL_ROOT/logs/$tag/configure.log"
  make -j "$JOBS" V=1 2>&1 | tee "$TRIAL_ROOT/logs/$tag/build.log"
  make check 2>&1 | tee "$TRIAL_ROOT/logs/$tag/check.log"
  make install 2>&1 | tee "$TRIAL_ROOT/logs/$tag/install.log"
  cp config.log "$TRIAL_ROOT/logs/$tag/config.log"
)
export MPI_LIB_DIRS="$MPI_PREFIX/lib:$UCX_PREFIX/lib"
{
  printf '%s\n' 'source "$TRIAL_ROOT/env.sh"'
  for name in MPI_PREFIX UCX_PREFIX MPI_LIB_DIRS; do
    printf 'export %s=%q\n' "$name" "${!name}"
  done
  cat <<'ENV'
export PATH="$MPI_PREFIX/bin:$UCX_PREFIX/bin:$GCC_PREFIX/bin:$BINUTILS_PREFIX/bin:$TRIAL_BASE_PATH"
export LD_LIBRARY_PATH="$MPI_LIB_DIRS:$GCC_LIB_DIRS${TRIAL_SITE_LIB_DIRS:+:$TRIAL_SITE_LIB_DIRS}"
export OMPI_MCA_pml=ucx
export OMPI_MCA_btl='^uct'
export OMPI_MCA_io=romio321
export OMPI_MCA_plm=slurm
export OMPI_MCA_ras=slurm
hash -r
ENV
} > "$envfile"
source "$envfile"
"$MPI_PREFIX/bin/ompi_info" --all > "$TRIAL_ROOT/logs/$tag/info.txt"
"$MPI_PREFIX/bin/ompi_info" --param pml ucx
"$MPI_PREFIX/bin/ompi_info" --param io all
"$MPI_PREFIX/bin/ompi_info" --param plm slurm
"$MPI_PREFIX/bin/ompi_info" --param ras slurm
"$MPI_PREFIX/bin/mpicc" --showme:command
"$MPI_PREFIX/bin/mpicc" --showme:compile
"$MPI_PREFIX/bin/mpicc" --showme:link
"$MPI_PREFIX/bin/mpifort" --showme:command
test "$(command -v mpirun)" = "$MPI_PREFIX/bin/mpirun"
test "$(command -v mpicc)" = "$MPI_PREFIX/bin/mpicc"
test "$("$MPI_PREFIX/bin/mpicc" --showme:command)" = "$CC"
test "$("$MPI_PREFIX/bin/mpifort" --showme:command)" = "$FC"
ldd "$MPI_PREFIX/bin/mpirun" > "$TRIAL_ROOT/logs/$tag/launcher-libraries.txt"
ldd "$MPI_PREFIX/lib/openmpi/mca_pml_ucx.so" \
  > "$TRIAL_ROOT/logs/$tag/ucx-component-libraries.txt"
declare -p AUTOTOOLS_CFLAGS AUTOTOOLS_CXXFLAGS AUTOTOOLS_FFLAGS AUTOTOOLS_LDFLAGS > "$TRIAL_ROOT/logs/$tag/flags.txt"
done
source "$TRIAL_ROOT/mpi-env.sh"
```

The wrapper commands must name the private GCC 12.5.0 drivers. Wrapper compile flags must not force an experiment control into every consuming package: hardening Open MPI itself should not silently inject its hardening flags into callers. Inspect the wrapper-data files and `--showme:*` output. If flags are injected, correct the wrapper configuration and requalify before the package matrix. Verify the `ucx` PML, `romio321` I/O, and Slurm launch/allocation components are present. The UCX component's `ldd` output must resolve `libucp`, `libuct`, `libucs`, and other UCX libraries to the private UCX prefix, with no missing dependencies or site MPI/AOCC substitutions. Inspect any user/site MCA parameter files for component-path overrides. `ompi_info` success alone is not a data-transfer test.

`mpi-env.sh` reestablishes the explicit baseline before activating MPI. Set recorded `UCX_TLS`, `UCX_NET_DEVICES`, and any deliberate runtime tuning **after** sourcing it. The Slurm component selections require a real allocation and prevent a successful SSH fallback from concealing missing Slurm integration. Keep these choices identical across package arms.

## 5. Verify two-node execution before benchmarking

Use a two-node scheduler allocation; for Slurm, obtain it with the site's account/partition options, for example `salloc -N 2 -n 2 -t 00:30:00`. Use `mpirun` within that allocation. Do not bypass the scheduler with an unapproved host list. The prefix/source/result paths must exist at the same absolute paths on both nodes.

```bash
cat > "$TRIAL_ROOT/bench/mpi_placement.h" <<'C'
#ifndef TRIAL_MPI_PLACEMENT_H
#define TRIAL_MPI_PLACEMENT_H
#include <mpi.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static void trial_mpi_placement(void) {
    int rank,size,len; char host[MPI_MAX_PROCESSOR_NAME]={0};
    MPI_Comm_rank(MPI_COMM_WORLD,&rank); MPI_Comm_size(MPI_COMM_WORLD,&size);
    MPI_Get_processor_name(host,&len);
    char *hosts=rank==0 ? calloc((size_t)size,MPI_MAX_PROCESSOR_NAME) : NULL;
    if(rank==0 && !hosts) MPI_Abort(MPI_COMM_WORLD,1);
    MPI_Gather(host,MPI_MAX_PROCESSOR_NAME,MPI_CHAR,hosts,MPI_MAX_PROCESSOR_NAME,
               MPI_CHAR,0,MPI_COMM_WORLD);
    if(rank==0) {
        int nodes=0;
        const char *en=getenv("TRIAL_EXPECTED_NODES"), *er=getenv("RANKS_PER_NODE");
        int expected=en ? atoi(en) : 0, rpn=er ? atoi(er) : 0;
        if((en && expected<1) || (er && rpn<1)) MPI_Abort(MPI_COMM_WORLD,1);
        for(int i=0;i<size;i++) {
            const char *h=hosts+(size_t)i*MPI_MAX_PROCESSOR_NAME;
            fprintf(stderr,"MPI_PLACEMENT rank=%d host=%s\n",i,h);
            int first=1, count=0;
            for(int j=0;j<size;j++) {
                if(!strcmp(h,hosts+(size_t)j*MPI_MAX_PROCESSOR_NAME)) {
                    count++; if(j<i) first=0;
                }
            }
            if(first) {
                nodes++;
                if(rpn && count!=rpn) MPI_Abort(MPI_COMM_WORLD,1);
            }
        }
        fprintf(stderr,"MPI_PLACEMENT nodes=%d ranks=%d\n",nodes,size);
        if(expected && nodes!=expected) MPI_Abort(MPI_COMM_WORLD,1);
        free(hosts);
    }
    MPI_Barrier(MPI_COMM_WORLD);
}
#endif
C
cat > "$TRIAL_ROOT/bench/mpi-smoke.c" <<'C'
#include <mpi.h>
#include <stdio.h>
#include "mpi_placement.h"
int main(int argc,char **argv) {
    int rank,size,sum,provided;
    MPI_Init_thread(&argc,&argv,MPI_THREAD_FUNNELED,&provided);
    trial_mpi_placement();
    MPI_Comm_rank(MPI_COMM_WORLD,&rank); MPI_Comm_size(MPI_COMM_WORLD,&size);
    MPI_Allreduce(&rank,&sum,1,MPI_INT,MPI_SUM,MPI_COMM_WORLD);
    if(provided<MPI_THREAD_FUNNELED || sum!=size*(size-1)/2) MPI_Abort(MPI_COMM_WORLD,1);
    char host[MPI_MAX_PROCESSOR_NAME]; int len;
    MPI_Get_processor_name(host,&len);
    printf("rank=%d size=%d host=%s sum=%d\n",rank,size,host,sum);
    MPI_Finalize(); return 0;
}
C
export TRIAL_EXPECTED_NODES=2 RANKS_PER_NODE=1
for p in full reference; do
activate_mpi_profile "$p"
profile_flags full  # one fixed qualification caller, not a benchmark arm
read -r -a cargs <<< "$EXE_CFLAGS"
read -r -a largs <<< "$EXE_LDFLAGS"
"$MPI_PREFIX/bin/mpicc" "${cargs[@]}" "$TRIAL_ROOT/bench/mpi-smoke.c" \
  "${largs[@]}" -o "$TRIAL_ROOT/bench/mpi-smoke-$p"
"$MPI_PREFIX/bin/mpirun" -np 2 --map-by ppr:1:node --bind-to core \
  --report-bindings --mca pml ucx --mca btl '^uct' \
  -x PATH -x LD_LIBRARY_PATH -x TRIAL_EXPECTED_NODES -x RANKS_PER_NODE -x UCX_LOG_LEVEL=info \
  "$TRIAL_ROOT/bench/mpi-smoke-$p" \
  2>&1 | tee "$TRIAL_ROOT/logs/mpi-two-node-$p.log"
done
source "$TRIAL_ROOT/mpi-env.sh"
```

Confirm distinct hostnames, the correct sum, and the selected UCX transport. UCX's informational logging is for qualification; remove it from timed runs. On each rank/node record `ucx_info -d`, `ldd` for the benchmark and the installed UCX PML component, and `ulimit -l`. Verify no system MPI/UCX is substituted. Keep runtime environment, transport/device selection, rank count, binding, and the MPI/UCX libraries fixed in library-only comparisons. Stack scope in 11 selects matched full/reference dependency arms. Do not add oversubscription to conceal an allocation mismatch.

Continue with [05 — Parallel FFTW and HDF5](05-parallel.md).
