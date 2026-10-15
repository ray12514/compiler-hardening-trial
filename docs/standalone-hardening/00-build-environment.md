# Build environment and system dependencies

Run this before the GCC bootstrap. The trial installs GCC, binutils, CMake, UCX, Open MPI, and payload libraries under a new writable `TRIAL_ROOT`. It uses the site's existing scheduler, operating-system development files, and approved fabric drivers. No command here installs OS packages, changes Slurm, replaces the site's AOCC/MPI/UCX, or edits shell startup files or site modules.

## 1. Keep the required master modules

Use a dedicated Bash shell in a site-approved build allocation. Retain the master modules required for that machine's scheduler, filesystem, and fabric. Unload optional compiler/MPI modules using the site's supported procedure. `module purge` is appropriate only if the site permits it and you then reload the required master modules; it is not a universal prerequisite. Sticky modules and dependencies can survive a purge.

```bash
bash
# Keep interactive error handling unchanged; build scripts run in child shells.
export TRIAL_ROOT=/absolute/path/to/hardening-trial
mkdir -p "$TRIAL_ROOT/logs/environment"
if type module >/dev/null 2>&1; then
    module list > "$TRIAL_ROOT/logs/environment/modules-before.txt" 2>&1
    # Use the site's actual module names and required order here.
    # module unload <optional-mpi-module> <optional-compiler-module>
    # Alternatively, if permitted: module purge; module load <required-masters>
    module list > "$TRIAL_ROOT/logs/environment/modules-build.txt" 2>&1
fi
type -a gcc g++ clang clang++ mpicc mpirun srun salloc || true
```

Do not infer that the installed AOCC MPI is compatible by changing `OMPI_CC` or another wrapper override. Open MPI wrappers are generated for the compiler used to build that installation, and C++/Fortran compatibility is particularly compiler-dependent. This trial builds its own MPI against its own GCC. [Open MPI v4 wrapper documentation](https://www.open-mpi.org/faq/?category=mpi-apps)

Use the installed `/usr/bin/gcc` and `/usr/bin/g++` as the bootstrap seed when both exist and pass the prerequisite and seed tests in 00. Record their versions. The resulting private GCC 12.5 drives the payload builds. AOCC's C/C++ drivers are an alternative seed only when needed and qualified, with their required runtime directories recorded. If no usable seed exists, use the compatible transferred-toolchain route in 00.

## 2. Select explicit search paths

Inspect the master modules and choose the directories below; do not copy the inherited `PATH` or `LD_LIBRARY_PATH`. Retain the real Slurm client directory and required site utility directories. Site runtime directories may contain approved scheduler/fabric dependencies, but must exclude other compilers, MPI, and UCX. System default loader/compiler search directories still exist; this is controlled dependency selection, not a container or isolated OS image.

Use colon-separated absolute directories without empty entries or trailing colons. An empty optional list is allowed; an empty entry inside a search path can select the current directory.

```bash
# Replace /usr/bin if the site's Slurm clients are installed elsewhere.
export SLURM_BINDIR=/usr/bin
export TRIAL_BASE_PATH="$SLURM_BINDIR:/usr/bin:/bin"
# Append specific approved utility directories when needed, e.g. site Python.
export TRIAL_SITE_LIB_DIRS=''
export TRIAL_SITE_PKGCONFIG_DIRS=''
export TRIAL_SITE_CMAKE_PREFIXES=''

# System GCC is the seed, not the payload compiler version being tested.
export SEED_CC=/usr/bin/gcc
export SEED_CXX=/usr/bin/g++
export TRIAL_SEED_LIB_DIRS=''
# Set this to the specific seed runtime directories if its binaries need them.
```

For an RDMA build, identify compatible site verbs/rdmacm headers and libraries. Use the explicit configure prefixes in 00b and add any required nonstandard runtime directories to `TRIAL_SITE_LIB_DIRS`. Do not load a site MPI or site UCX to supply these dependencies. The default TCP/shared-memory bring-up does not establish RDMA performance.

## 3. Save the baseline and clear build overrides

This helper clears compiler/discovery overrides and inherited MPI/UCX settings while retaining master-module metadata, `SLURM_*` allocation/configuration variables, and ordinary site/account settings. Review any site-required exception before changing this helper. Source it in the build/launch shell, not inside an already running MPI rank.

```bash
{
    for name in TRIAL_BASE_PATH SLURM_BINDIR TRIAL_SITE_LIB_DIRS \
                TRIAL_SITE_PKGCONFIG_DIRS TRIAL_SITE_CMAKE_PREFIXES; do
        printf 'export %s=%q\n' "$name" "${!name}"
    done
    cat <<'ENV'
trial_clear_build_overrides() {
    unset CC CXX FC F77 F90 CPP CFLAGS CXXFLAGS FFLAGS FCFLAGS CPPFLAGS LDFLAGS LIBS
    unset CPATH C_INCLUDE_PATH CPLUS_INCLUDE_PATH OBJC_INCLUDE_PATH LIBRARY_PATH
    unset GCC_EXEC_PREFIX COMPILER_PATH LD_PRELOAD LD_AUDIT LD_RUN_PATH
    unset PKG_CONFIG_PATH PKG_CONFIG_LIBDIR PKG_CONFIG_SYSROOT_DIR
    unset CMAKE_PREFIX_PATH CMAKE_MODULE_PATH CMAKE_TOOLCHAIN_FILE CONFIG_SITE
    unset BASH_ENV ENV PYTHONPATH PYTHONHOME MAKEFLAGS MFLAGS
    unset MPI_HOME MPI_ROOT MPI_DIR MPI_PATH MPI_BIN MPICH_DIR MPICH_ROOT
    local trial_var
    while IFS= read -r trial_var; do
        case "$trial_var" in
            OMPI_*|ORTE_*|OPAL_*|PMIX_*|UCX_*|I_MPI_*|MPICH_*) unset "$trial_var" ;;
        esac
    done < <(compgen -e)
    export PKG_CONFIG_PATH="$TRIAL_SITE_PKGCONFIG_DIRS"
    export CMAKE_PREFIX_PATH="$TRIAL_SITE_CMAKE_PREFIXES"
}
trial_clear_build_overrides
export PATH="$TRIAL_BASE_PATH"
if test -n "$TRIAL_SITE_LIB_DIRS"; then
    export LD_LIBRARY_PATH="$TRIAL_SITE_LIB_DIRS"
else
    unset LD_LIBRARY_PATH
fi
hash -r
ENV
} > "$TRIAL_ROOT/site-env.sh"
source "$TRIAL_ROOT/site-env.sh"
printf '%s\n' "PATH=$PATH" "LD_LIBRARY_PATH=${LD_LIBRARY_PATH-}" \
  "PKG_CONFIG_PATH=$PKG_CONFIG_PATH" "CMAKE_PREFIX_PATH=$CMAKE_PREFIX_PATH" \
  > "$TRIAL_ROOT/logs/environment/baseline-paths.txt"
for tool in make tar xz bzip2 bash awk sed diff sha256sum; do
    command -v "$tool"
done
# For the Slurm route in 00b, these must be the existing site clients.
test -x "$SLURM_BINDIR/srun"
test -x "$SLURM_BINDIR/salloc"
"$SLURM_BINDIR/srun" --version > "$TRIAL_ROOT/logs/environment/slurm-version.txt"
```

Follow 00 next. Before its seed smoke test, temporarily add the seed compiler's explicit directories and runtime paths as shown there. The generated `env.sh` reactivates this baseline and then sets only private GCC/binutils paths plus approved site dependencies. `mpi-env.sh` adds only private Open MPI/UCX paths and the recorded MPI settings. Sourcing these files changes that shell and its children; it does not change other users' environments.

In every new build/test allocation, establish the required master modules first and then source `env.sh` and, for parallel work, `mpi-env.sh`. Do not load a compiler/MPI module afterward. Record `module list`, actual compiler/wrapper commands, and `ldd` output on the compute nodes. A fresh environment also requires fresh build directories and CMake caches; environment changes do not repair an existing configured build.
