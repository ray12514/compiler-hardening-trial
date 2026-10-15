# 01 — Common GCC 12.5.0 profiles and measurements

**Normal route:** follow the [README](README.md), then run `"$TRIAL_ROOT/runner/trial" setup`. The driver runs the applicable blocks below in child shells, including prerequisites. These numbered sections are recipe references; do not paste all of them after using the driver.

Prerequisite: [00 — GCC bootstrap](00-gcc-bootstrap.md). Execute these setup blocks once in Bash after sourcing `env.sh`. All package runbooks source the resulting `profiles.sh`.

## 1. Create explicit profiles

The default **listed** set matches the flags supplied for the white-paper discussion. GCC 12.5.0 does not have `-fhardened`; the flags are explicit. `full` means all applicable controls in the selected set. FORTIFY applies to supported C/C++ libc calls; it does not add Fortran array-bounds checks.

| Output | Compile controls in `full` | Link controls in `full` |
|---|---|---|
| FFTW/HDF5 shared C libraries | `-fPIC -fstack-protector-strong -U_FORTIFY_SOURCE -D_FORTIFY_SOURCE=2` | `-Wl,-z,relro -Wl,-z,now` |
| LAPACK shared Fortran library | `-fPIC -fstack-protector-strong` | `-Wl,-z,relro -Wl,-z,now` |
| Fixed C benchmark executables | `-fPIE -fstack-protector-strong -U_FORTIFY_SOURCE -D_FORTIFY_SOURCE=2` | `-pie -Wl,-z,relro -Wl,-z,now` |
| Fixed Fortran benchmark executable | `-fPIE -fstack-protector-strong` | `-pie -Wl,-z,relro -Wl,-z,now` |

`-U_FORTIFY_SOURCE` clears an inherited definition before setting level 2. All arms retain the same `-O3`, CPU target, warnings, library PIC, and non-executable stack. RELRO/NOW are passed through the GCC driver to GNU ld using **`-Wl,-z,...`**, not `-WL` or `-d`. The library-only measurements keep the full benchmark executable fixed. Stack scope in 11 switches matched callers and dependencies as well. [07](07-consumer-pie.md) measures executable PIE separately with the full libraries fixed.

The earlier broader trial remains available as `HARDENING_SET=extended`. It adds all-function stack protection, stack-clash protection, C/C++ local initialization, x86 compiler control-flow protection, and C++ libstdc++ assertions, with an explicitly selected FORTIFY level. Those additions are separate research controls; the supplied list does not establish that they are required.

| Profile | Change relative to full |
|---|---|
| `full` | All applicable controls in the selected listed or extended set |
| `reference` | All variable controls disabled; optimization, PIC, warnings, and non-executable stack retained |
| `stack-all` | Optional: replace strong stack protection with all-function protection |
| `minus-stack` | Disable stack protector |
| `minus-fortify` | Disable C/C++ FORTIFY |
| `stack-strong` | Extended set only: replace all-function protection with strong protection |
| `minus-clash` | Extended set only: disable stack-clash protection |
| `minus-init` | Extended set only: disable C/C++ automatic local initialization |
| `minus-cf` | Extended set only: disable x86 compiler control-flow protection |
| `minus-relro` | Disable RELRO, retain eager binding |
| `minus-now` | Disable eager binding, retain RELRO |
| `minus-pie` | Consumer executable only: disable PIE, retain the full library and other controls |

PIC remains on for shared libraries. A non-executable stack remains on throughout. In the extended experiment, `-fcf-protection=full` is compiler-generated x86 CET support, not proof that hardware shadow-stack enforcement is active.

```bash
source "$TRIAL_ROOT/env.sh"
cat > "$TRIAL_ROOT/profiles.sh" <<'SH'
profile_flags() {
    local p=${1:?profile required}
    local mode=${HARDENING_SET:-listed}
    local stack=-fstack-protector-strong clash=-fno-stack-clash-protection
    local cf=-fcf-protection=none init=-ftrivial-auto-var-init=uninitialized
    local fortify="-U_FORTIFY_SOURCE -D_FORTIFY_SOURCE=$FORTIFY_LEVEL"
    local assertions=-U_GLIBCXX_ASSERTIONS
    local relro=-Wl,-z,relro now=-Wl,-z,now pie=-fPIE pielink=-pie
    case "$mode" in
      listed)
        if test "$FORTIFY_LEVEL" != 2; then
          printf '%s\n' 'The listed set requires FORTIFY_LEVEL=2.' >&2; return 1
        fi ;;
      extended)
        stack=-fstack-protector-all; clash=-fstack-clash-protection
        cf="-fcf-protection=$CF_MODE"; init=-ftrivial-auto-var-init=zero
        assertions=-D_GLIBCXX_ASSERTIONS ;;
      *) printf 'Unknown HARDENING_SET: %s\n' "$mode" >&2; return 1 ;;
    esac
    case "$p" in
      stack-strong|minus-clash|minus-init|minus-cf)
        if test "$mode" != extended; then
          printf 'Profile %s requires HARDENING_SET=extended.\n' "$p" >&2; return 1
        fi ;;
    esac
    case "$p" in
      full) ;;
      reference)
        stack=-fno-stack-protector; clash=-fno-stack-clash-protection
        cf=-fcf-protection=none; init=-ftrivial-auto-var-init=uninitialized
        fortify=-U_FORTIFY_SOURCE; assertions=-U_GLIBCXX_ASSERTIONS
        relro=-Wl,-z,norelro; now=-Wl,-z,lazy; pie=-fno-pie; pielink=-no-pie ;;
      stack-strong) stack=-fstack-protector-strong ;;
      stack-all) stack=-fstack-protector-all ;;
      minus-stack) stack=-fno-stack-protector ;;
      minus-fortify) fortify=-U_FORTIFY_SOURCE ;;
      minus-clash) clash=-fno-stack-clash-protection ;;
      minus-init) init=-ftrivial-auto-var-init=uninitialized ;;
      minus-cf) cf=-fcf-protection=none ;;
      minus-relro) relro=-Wl,-z,norelro ;;
      minus-now) now=-Wl,-z,lazy ;;
      minus-pie) pie=-fno-pie; pielink=-no-pie ;;
      *) printf 'Unknown profile: %s\n' "$p" >&2; return 1 ;;
    esac
    BASE_OPT="-O3 -g -march=$CPU_TARGET -mtune=generic -fno-lto"
    C_CONTROL="$stack $clash $cf $init $fortify -Wformat -Werror=format-security"
    F_CONTROL="$stack $clash $cf"
    CFLAGS="$BASE_OPT $C_CONTROL -fPIC"
    CXXFLAGS="$CFLAGS $assertions"
    FFLAGS="$BASE_OPT $F_CONTROL -fPIC"
    FCFLAGS="$FFLAGS"
    CPPFLAGS=''
    SHARED_LDFLAGS="$relro $now -Wl,-z,noexecstack -Wl,--enable-new-dtags"
    EXE_CFLAGS="$BASE_OPT $C_CONTROL $pie"
    EXE_CXXFLAGS="$EXE_CFLAGS $assertions"
    EXE_FFLAGS="$BASE_OPT $F_CONTROL $pie"
    EXE_LDFLAGS="$SHARED_LDFLAGS $pielink"
    export CFLAGS CXXFLAGS FFLAGS FCFLAGS CPPFLAGS SHARED_LDFLAGS
    export EXE_CFLAGS EXE_CXXFLAGS EXE_FFLAGS EXE_LDFLAGS
    if test -n "${TRIAL_DRIVER_SCRIPT:-}"; then
        local trial_assignments
        trial_assignments=$("$TRIAL_DRIVER_PYTHON" "$TRIAL_DRIVER_SCRIPT" --effective-flags \
          "${TRIAL_COMPONENT_ID:-global}" "$p") || return 1
        eval "$trial_assignments"
    fi
}
mpi_profile_prefixes() {
    case "${1:?profile required}" in
      reference)
        export UCX_PREFIX="$TRIAL_ROOT/install/ucx-1.16.0-reference"
        export MPI_PREFIX="$TRIAL_ROOT/install/openmpi-4.1.8-ucx-reference" ;;
      full|minus-*)
        export UCX_PREFIX="$TRIAL_ROOT/install/ucx-1.16.0-fixed"
        export MPI_PREFIX="$TRIAL_ROOT/install/openmpi-4.1.8-ucx-fixed" ;;
      *) printf 'No MPI dependency mapping for %s\n' "$1" >&2; return 1 ;;
    esac
}
activate_mpi_profile() {
    local file="$TRIAL_ROOT/mpi-env.sh"
    if test "${1:?profile required}" = reference; then
        file="$TRIAL_ROOT/mpi-env-reference.sh"
    fi
    test -f "$file" || { printf 'Missing MPI environment: %s\n' "$file" >&2; return 1; }
    source "$file"
}
autotools_flags() {
    # Libtool appends -fPIC when compiling shared objects. Executable compilation
    # uses EXE_*FLAGS; conditional specs add PIE only on executable links.
    local link=-no-pie
    : "${1:?profile required}"
    case " $EXE_LDFLAGS " in *" -pie "*) link=-pie ;; esac
    local spec="$TRIAL_ROOT/bench/probes/autotools-$1.specs"
    mkdir -p "$TRIAL_ROOT/bench/probes"
    cat > "$spec" <<SPEC
*self_spec:
+ %{!static:%{!static-pie:%{!shared:%{!r:%{!c:%{!S:%{!E:$link}}}}}}}

SPEC
    AUTOTOOLS_CFLAGS="$EXE_CFLAGS"
    AUTOTOOLS_CXXFLAGS="$EXE_CXXFLAGS"
    AUTOTOOLS_FFLAGS="$EXE_FFLAGS"
    AUTOTOOLS_LDFLAGS="$SHARED_LDFLAGS -specs=$spec"
}
LIB_PROFILES=(full reference minus-stack minus-fortify minus-relro minus-now)
LAPACK_PROFILES=(full reference minus-stack minus-relro minus-now)
if test "${HARDENING_SET:-listed}" = extended; then
    LIB_PROFILES+=(stack-strong minus-clash minus-init minus-cf)
    LAPACK_PROFILES+=(stack-strong minus-clash minus-cf)
fi
SH
source "$TRIAL_ROOT/profiles.sh"
```

Use the explicit flags in the [GCC 12.5 instrumentation manual](https://gcc.gnu.org/onlinedocs/gcc-12.5.0/gcc/Instrumentation-Options.html), [automatic initialization documentation](https://gcc.gnu.org/onlinedocs/gcc-12.5.0/gcc/Optimize-Options.html), and [glibc FORTIFY documentation](https://sourceware.org/glibc/manual/latest/html_node/Source-Fortification.html). The full set is a candidate for this experiment, not a claim that every option is mandatory under your organizational profile.

## 2. Qualify flags before expensive builds

Start with the complete listed profile and its matched reference. Record the exact approved flag list, language/output applicability, compiler versions, commands and artifact checks. The supplied list is the current input; do not guess additional SOP requirements. [11](11-stack-comparison.md) defines the first stack comparison; [08](08-slurm-campaign.md) contains individual-control hypotheses for later investigation.

The normal `trial setup` command performs these checks automatically. It retries a compiler probe only when the diagnostic explicitly rejects a requested control, records the diagnostic and exact effective vectors in `runner/policy.json` and `runner/qualification.json`, and labels a reduced result `compatible-HASH`. The `full` directory then denotes the requested arm; the recorded effective identity defines the actual experiment. An unrelated compile, link, runtime or correctness failure stops with its log.

For the manual route, if a flag fails, retain the command/error and package/version in `logs/compatibility.tsv` (tab-separated columns: component, profile, language, requested_flag, result, reason, action, procedure_commit). Resolve the failure before timing that component. An agreed reduced profile gets a new identity and fresh affected builds; never silently relabel it `full`. A Fortran FORTIFY non-applicability entry is different from a C build rejecting a required control. Compiler acceptance alone is not artifact verification.


Run on the execution CPU, not only the login node. This checks compiler acceptance, FORTIFY implementation level, and smoke execution. It does not establish that every package function receives a check.

```bash
mkdir -p "$TRIAL_ROOT/bench/probes" "$TRIAL_ROOT/logs/profiles"
cat > "$TRIAL_ROOT/bench/probes/probe.c" <<'C'
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#if defined(_FORTIFY_SOURCE) && __USE_FORTIFY_LEVEL != _FORTIFY_SOURCE
#error Requested FORTIFY level is not implemented by these headers/compiler
#endif
int main(int argc, char **argv) {
    char b[64];
    snprintf(b, sizeof b, "%s", argc > 1 ? argv[1] : "probe");
    puts(b);
    return 0;
}
C
cp "$TRIAL_ROOT/bench/probes/probe.c" "$TRIAL_ROOT/bench/probes/probe.cc"
QUALIFY_PROFILES=(full reference)  # add selected removals before their follow-up builds
for p in "${QUALIFY_PROFILES[@]}"; do
    profile_flags "$p"
    read -r -a cargs <<< "$EXE_CFLAGS"
    read -r -a cxxargs <<< "$EXE_CXXFLAGS"
    read -r -a largs <<< "$EXE_LDFLAGS"
    read -r -a fargs <<< "$EXE_FFLAGS"
    {
      declare -p CFLAGS CXXFLAGS FFLAGS SHARED_LDFLAGS EXE_CFLAGS EXE_CXXFLAGS EXE_FFLAGS EXE_LDFLAGS
      "$CC" -Werror "${cargs[@]}" "$TRIAL_ROOT/bench/probes/probe.c" \
        "${largs[@]}" -o "$TRIAL_ROOT/bench/probes/c-$p"
      "$CXX" -Werror "${cxxargs[@]}" "$TRIAL_ROOT/bench/probes/probe.cc" \
        "${largs[@]}" -o "$TRIAL_ROOT/bench/probes/cxx-$p"
      "$FC" -Werror "${fargs[@]}" "$TRIAL_ROOT/bench/gcc-fortran-smoke.f90" \
        "${largs[@]}" -o "$TRIAL_ROOT/bench/probes/f-$p"
      "$TRIAL_ROOT/bench/probes/c-$p"
      "$TRIAL_ROOT/bench/probes/cxx-$p"
      "$TRIAL_ROOT/bench/probes/f-$p"
      readelf -hW "$TRIAL_ROOT/bench/probes/c-$p"
      readelf -lW "$TRIAL_ROOT/bench/probes/c-$p"
      readelf -dW "$TRIAL_ROOT/bench/probes/c-$p"
      readelf -nW "$TRIAL_ROOT/bench/probes/c-$p"
    } > "$TRIAL_ROOT/logs/profiles/$p.log" 2>&1
done
```

The complete listed set requires implemented FORTIFY level 2. GCC's acceptance of a macro alone is insufficient. The driver records an unavailable FORTIFY implementation as a reduced experiment before building. The manual route must make the same distinction explicitly; a reduced result is not evidence for the complete listed set.

For the optional broader experiment, choose a **new trial root** before building and set `HARDENING_SET=extended`, `FORTIFY_LEVEL=3`, and `CF_MODE=full` in its `env.sh`. If its FORTIFY 3 qualification fails, explicitly select 2 and record the choice. If `CF_MODE=none`, omit the no-op `minus-cf` comparison. Re-source `profiles.sh` after changing the set so its variant arrays match. These settings do not alter already compiled binaries.

The previous version of these runbooks used `full` for the broader set. Existing builds/results from that version must retain their old identity. Rebuild under a new root for the listed set; do not combine the old full libraries with new reference/removal builds.

Expected artifact distinctions: full probe executable is ELF `DYN`/PIE; reference and minus-PIE are `EXEC`. Full has a `GNU_RELRO` segment and a `BIND_NOW`/`NOW` dynamic flag; minus-RELRO lacks the former, minus-NOW lacks the latter. `GNU_STACK` should not have execute permission in any arm. GNU properties and `endbr64` disassembly help inspect CET code generation, but object property merging and runtime enablement also matter. Stack-protector and `_chk` symbols may occur only when the package actually needs them; their absence alone is not proof the flags were lost.

### Qualify mixed Autotools library/tool linking

FFTW, UCX and Open MPI use Libtool to build shared libraries and executables together. `autotools_flags` uses executable compile settings and a per-invocation GCC specs file that selects `-pie`/`-no-pie` only for dynamic executable links. Libtool's shared-object compilation must append `-fPIC`, and shared links must contain `-shared`. This does not modify GCC defaults or its installed specs; the file is supplied in build `LDFLAGS`, never in the MPI wrapper compiler command. [GCC specs](https://gcc.gnu.org/onlinedocs/gcc-12.5.0/gcc/Spec-Files.html), [GCC 12 driver source](https://gnu.googlesource.com/gcc/+/refs/heads/releases/gcc-12/gcc/gcc.cc), and [Fedora's PIE specs example](https://fedoraproject.org/wiki/Changes/Harden_All_Packages).

```bash
for p in full reference; do
    profile_flags "$p"
    autotools_flags "$p"
    read -r -a cargs <<< "$AUTOTOOLS_CFLAGS"
    read -r -a largs <<< "$AUTOTOOLS_LDFLAGS"
    "$CC" "${cargs[@]}" "$TRIAL_ROOT/bench/probes/probe.c" \
      "${largs[@]}" -o "$TRIAL_ROOT/bench/probes/tool-$p"
    # Mimic Libtool's final shared-object PIC option, then its shared link.
    "$CC" "${cargs[@]}" -fPIC -c "$TRIAL_ROOT/bench/probes/probe.c" \
      -o "$TRIAL_ROOT/bench/probes/shared-$p.o"
    "$CC" -shared "$TRIAL_ROOT/bench/probes/shared-$p.o" "${largs[@]}" \
      -o "$TRIAL_ROOT/bench/probes/shared-$p.so"
    "$TRIAL_ROOT/bench/probes/tool-$p"
    readelf -hW "$TRIAL_ROOT/bench/probes/tool-$p"
    readelf -dW "$TRIAL_ROOT/bench/probes/shared-$p.so"
done
```

Require PIE on the full tool, EXEC on the reference tool, and a shared object without the PIE dynamic flag. Retain these results with `logs/profiles`; inspect actual package compile/link commands after the builds. Static links and relocatable links are outside this dynamic-library trial.

## 3. Inspect each installed variant

Run this with the actual shared library path from its package runbook. Keep its output alongside compile commands and CMake cache/configure output.

```bash
LIBRARY=/absolute/path/to/installed/lib/library.so
test -f "$LIBRARY"
readelf -lW "$LIBRARY"
readelf -dW "$LIBRARY"
readelf -nW "$LIBRARY"
nm -D "$LIBRARY" | awk '/__stack_chk_fail|_chk/ {print}'
objdump -d "$LIBRARY" | awk '/endbr64/ {n++} END {print "endbr64 instructions:", n+0}'
```

Do not use shell success as the only flag audit: look at actual compile/link commands and ELF properties. If a build system overrides flags, correct it before benchmarking.

## 4. Create the paired timing harness

The package runbooks create one fixed driver each. Drivers print CSV rows `phase,seconds,error` and fail on a correctness error. The harness switches the library path, warms each variant once, alternates full/comparator order across fresh process pairs, retains raw results, and computes a bootstrap interval for the geometric mean of paired runtime ratios. It also records arithmetic means and sample standard deviations in seconds for each arm, plus the sample standard deviation of pairwise runtime changes in percentage points. It uses Python's standard library only. Ten pairs are a pilot; [08](08-slurm-campaign.md#repeatability-and-a-manageable-first-assessment) defines repetitions across allocations and nodes.

Every run also records `process_elapsed`, including process launch, dynamic loading, the workload, correctness checks, output capture, and exit. Inspect it alongside kernel phases when assessing startup-sensitive controls such as NOW. The [PIE procedure](07-consumer-pie.md) uses a second caller and keeps both arms on the full libraries; its summary records that scope explicitly.

```bash
cat > "$TRIAL_ROOT/bench/paired.py" <<'PY'
import csv, hashlib, json, math, os, pathlib, random, re, shlex, statistics, subprocess, sys, time
package, executable, case, *args = sys.argv[1:]
root = pathlib.Path(os.environ['TRIAL_ROOT'])
comparator = os.environ.get('COMPARE', 'reference')
pairs = int(os.environ.get('PAIRS', '10'))
if pairs < 2:
    raise SystemExit('PAIRS must be at least 2')
profiles = ('full', comparator)
if comparator == 'full':
    raise SystemExit('COMPARE must differ from full')
scope = os.environ.get('TRIAL_SCOPE', 'library')
if scope not in ('library','stack'):
    raise SystemExit('TRIAL_SCOPE must be library or stack')
managed_builds = {}
managed_packages = [package]
if package == 'lapack': managed_packages += ['blas']
if package.endswith('-mpi'): managed_packages += ['openmpi','ucx']
for managed_package in managed_packages:
    for arm in ('full', comparator):
        state_path = root/'runner/state'/f'{managed_package}-{arm}.json'
        if state_path.exists():
            state = json.loads(state_path.read_text())
            for path, expected_hash in state['artifacts'].items():
                artifact = root/path
                if not artifact.is_file() or hashlib.sha256(artifact.read_bytes()).hexdigest() != expected_hash:
                    raise SystemExit(f'Managed artifact changed: {artifact}; do not relabel old builds')
            managed_builds[f'{managed_package}-{arm}'] = {k:v for k,v in state.items() if k != 'artifacts'}
other_executable = os.environ.get('COMPARE_EXECUTABLE', '')
consumer = comparator == 'minus-pie'
if consumer and not other_executable:
    raise SystemExit('PIE comparison requires its separately built caller')
if scope == 'stack' and (comparator != 'reference' or not other_executable):
    raise SystemExit('Stack scope requires reference and its separately built caller; see 11')
if other_executable and not (consumer or scope == 'stack'):
    raise SystemExit('Caller override requires consumer PIE or stack scope')
drivers = {'full': executable, comparator: other_executable or executable}
library_profiles = {p: 'full' if consumer else p for p in profiles}
envs, launchers, dependencies = {}, {}, {}
mpi_np = int(os.environ.get('MPI_NP', '0'))
if mpi_np < 0: raise SystemExit('MPI_NP must be nonnegative')
for profile in profiles:
    prefix = root / 'install' / package / library_profiles[profile] / 'lib'
    if not prefix.is_dir():
        raise SystemExit(f'Missing installed variant: {prefix}')
    env = os.environ.copy()
    dep_profile = profile if scope == 'stack' else 'full'
    runtime = ''
    expected = [str(prefix.parent)]
    launcher = []
    if mpi_np:
        suffix = 'reference' if dep_profile == 'reference' else 'fixed'
        mpi = root / 'install' / f'openmpi-4.1.8-ucx-{suffix}'
        ucx = root / 'install' / f'ucx-1.16.0-{suffix}'
        if not (mpi/'bin/mpirun').is_file() or not (ucx/'lib').is_dir():
            raise SystemExit('Missing matching MPI/UCX stack')
        runtime = f'{mpi}/lib:{ucx}/lib'
        env['PATH'] = f'{mpi}/bin:{ucx}/bin:' + os.environ['PATH']
        env['TRIAL_MPI_PREFIX'], env['TRIAL_UCX_PREFIX'] = str(mpi), str(ucx)
        env['OMPI_MCA_mca_base_component_path'] = str(mpi/'lib/openmpi')
        expected.append(str(mpi))
        launcher = [str(mpi/'bin/mpirun'), '-np', str(mpi_np), '--map-by',
                    os.environ.get('MPI_MAP', 'ppr:1:node'), '--bind-to', 'core',
                    '--mca', 'pml', 'ucx', '--mca', 'btl', '^uct',
                    '-x', 'PATH', '-x', 'LD_LIBRARY_PATH', '-x', 'OMPI_MCA_io',
                    '-x', 'OMPI_MCA_mca_base_component_path']
        for name in ('UCX_TLS','UCX_NET_DEVICES','TRIAL_EXPECTED_NODES','RANKS_PER_NODE'):
            if name in os.environ: launcher += ['-x', name]
        launcher += shlex.split(os.environ.get('MPI_EXTRA_ARGS', ''))
        if scope == 'stack':
            for name in ('TRIAL_MPI_PREFIX','TRIAL_UCX_PREFIX','TRIAL_LIBRARY_PREFIX'):
                launcher += ['-x', name]
            launcher += ['/bin/bash', str(root/'bench/rank-exec.sh')]
        env['TRIAL_LIBRARY_PREFIX'] = str(prefix.parent)
    if package == 'lapack':
        blas = root / 'install' / 'blas' / dep_profile
        if not (blas/'lib/libblas.so').is_file():
            raise SystemExit(f'Missing BLAS: {blas}')
        runtime = str(blas/'lib')
        expected.append(str(blas))
    env['LD_LIBRARY_PATH'] = ':'.join(x for x in
        (str(prefix), runtime, os.environ['GCC_LIB_DIRS'],
         os.environ.get('TRIAL_SITE_LIB_DIRS', '')) if x)
    envs[profile], launchers[profile], dependencies[profile] = env, launcher, expected
result_root = pathlib.Path(os.environ.get('RESULT_ROOT', str(root / 'results')))
outdir = result_root / package / case / comparator
outdir.mkdir(parents=True, exist_ok=True)
raw = outdir / 'raw.csv'
if raw.exists():
    raise SystemExit(f'Results already exist: {raw}; select a new case label')
def require_family(text, pattern, prefix, label):
    paths = re.findall(pattern + r'\S*\s+=>\s+(\S+)', text)
    if not paths or any(not path.startswith(prefix + '/lib/') for path in paths):
        raise SystemExit(f'Wrong or mixed {label} dependency')
for profile in profiles:
    proc = subprocess.run(['ldd', drivers[profile]], env=envs[profile], text=True,
                          capture_output=True, check=True)
    (outdir / f'loaded-{profile}.txt').write_text(proc.stdout + proc.stderr)
    if 'not found' in proc.stdout:
        raise SystemExit(f'Missing runtime dependency for {profile}')
    if any(path + '/lib/' not in proc.stdout for path in dependencies[profile]):
        raise SystemExit(f'ldd did not select the requested dependencies for {profile}')
    family = 'libfftw3' if package.startswith('fftw') else 'libhdf5' if package.startswith('hdf5') else 'liblapack'
    require_family(proc.stdout, family, dependencies[profile][0], package)
    if package == 'lapack': require_family(proc.stdout, 'libblas', dependencies[profile][1], 'BLAS')
    if mpi_np:
        require_family(proc.stdout, r'lib(?:mpi|open-rte|open-pal)', dependencies[profile][1], 'MPI')
        check = subprocess.run(['ldd', launchers[profile][0]], env=envs[profile], text=True,
                               capture_output=True, check=True)
        (outdir / f'launcher-loaded-{profile}.txt').write_text(check.stdout + check.stderr)
        require_family(check.stdout, r'lib(?:mpi|open-rte|open-pal)', dependencies[profile][1], 'MPI launcher')
def run(profile):
    started = time.perf_counter()
    proc = subprocess.run([*launchers[profile], drivers[profile], *args], env=envs[profile], text=True,
                          capture_output=True)
    process_elapsed = time.perf_counter() - started
    with (outdir / 'driver.log').open('a') as f:
        f.write(f'profile={profile} driver={drivers[profile]} args={args!r}\n{proc.stdout}{proc.stderr}\n')
    proc.check_returncode()
    if mpi_np and os.environ.get('TRIAL_EXPECTED_NODES'):
        placement = re.findall(r'MPI_PLACEMENT nodes=(\d+) ranks=(\d+)', proc.stderr)
        expected = (int(os.environ['TRIAL_EXPECTED_NODES']), mpi_np)
        if len(placement)!=1 or tuple(map(int,placement[0]))!=expected:
            raise RuntimeError('Missing or incorrect MPI placement evidence; rebuild/qualify the caller')
    selected_hosts = os.environ.get('TRIAL_SELECTED_HOSTS', '')
    if mpi_np and selected_hosts:
        ranks = re.findall(r'MPI_PLACEMENT rank=(\d+) host=(\S+)', proc.stderr)
        actual_hosts = {host.split('.')[0] for _,host in ranks}
        expected_hosts = {host.split('.')[0] for host in selected_hosts.split(',')}
        if len(ranks)!=mpi_np or {int(rank) for rank,_ in ranks}!=set(range(mpi_np)) or actual_hosts!=expected_hosts:
            raise RuntimeError('MPI ranks did not run on the selected host subset')
    rows = []
    for phase, seconds, error in csv.reader(proc.stdout.splitlines()):
        seconds, error = float(seconds), float(error)
        if not math.isfinite(seconds) or seconds <= 0 or not math.isfinite(error):
            raise RuntimeError('Invalid measurement')
        rows.append((phase, seconds, error))
    if not rows or len({r[0] for r in rows}) != len(rows):
        raise RuntimeError('Missing or duplicate measurement phase')
    if 'process_elapsed' in {r[0] for r in rows}:
        raise RuntimeError('Reserved process_elapsed phase')
    rows.append(('process_elapsed', process_elapsed, 0.0))
    return rows
for profile in profiles:
    run(profile)
data = {}
with raw.open('w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['pair', 'order', 'package', 'case', 'profile', 'phase', 'seconds', 'error'])
    for pair in range(pairs):
        order = profiles if pair % 2 == 0 else profiles[::-1]
        data[pair] = {}
        for position, profile in enumerate(order):
            rows = run(profile)
            data[pair][profile] = {phase: seconds for phase, seconds, _ in rows}
            for phase, seconds, error in rows:
                writer.writerow([pair, position, package, case, profile, phase, seconds, error])
            f.flush()
phases = set(data[0]['full'])
if any(set(values[p]) != phases for values in data.values() for p in profiles):
    raise RuntimeError('Phases differ across runs')
rng = random.Random(20261006)
summary = {}
for phase in sorted(phases):
    full_times = [v['full'][phase] for v in data.values()]
    comparator_times = [v[comparator][phase] for v in data.values()]
    ratios = [a/b for a,b in zip(full_times, comparator_times)]
    logs = [math.log(r) for r in ratios]
    ratio = math.exp(statistics.mean(logs))
    samples = sorted(math.exp(statistics.mean(rng.choices(logs, k=pairs)))
                     for _ in range(10000))
    summary[phase] = {'pairs': pairs, 'runtime_ratio_full_over_comparator': ratio,
                      'full_runtime_seconds_mean': statistics.mean(full_times),
                      'full_runtime_seconds_stdev': statistics.stdev(full_times),
                      'comparator_runtime_seconds_mean': statistics.mean(comparator_times),
                      'comparator_runtime_seconds_stdev': statistics.stdev(comparator_times),
                      'paired_runtime_increase_stdev_percent_points': statistics.stdev(
                          [100*(r-1) for r in ratios]),
                      'full_runtime_seconds_geomean': math.exp(statistics.mean(
                          math.log(v['full'][phase]) for v in data.values())),
                      'comparator_runtime_seconds_geomean': math.exp(statistics.mean(
                          math.log(v[comparator][phase]) for v in data.values())),
                      'full_runtime_increase_percent': 100*(ratio-1),
                      'bootstrap_95_percent_interval': [100*(samples[250]-1),
                                                        100*(samples[9749]-1)]}
record = {'managed_builds': managed_builds,
          'effective_profile_ids': sorted({v['effective_profile']['identity'] for v in managed_builds.values()}),
          'package': package, 'case': case, 'comparator': comparator,
          'primary_phase': os.environ.get('PRIMARY_PHASE',''),
          'context': {name: os.environ.get(name, '') for name in (
              'CAMPAIGN_ID','RUN_ID','TRIAL_RUN_LABEL','TRIAL_REPLICATE_ID','TRIAL_EXPECTED_NODES','RANKS_PER_NODE',
              'MPI_NP','MPI_MAP','SCALING_MODE','IO_DIR','CPUSET','THREAD_CPUSET',
              'TRIAL_SELECTED_HOSTS','TRIAL_ALLOCATION_MODE','TRIAL_REPEAT_SCOPE',
              'SLURM_JOB_ID','SLURM_JOB_NODELIST','SLURM_JOB_NUM_NODES','SLURM_STEP_ID',
              'TRIAL_REGRESSION_LIMIT_PERCENT','UCX_TLS','UCX_NET_DEVICES')},
          'hardening_set': os.environ.get('HARDENING_SET', 'listed'),
          'fortify_level': int(os.environ.get('FORTIFY_LEVEL', '2')),
          'scope': 'consumer-pie' if consumer else scope,
          'driver_by_profile': drivers,
          'driver_sha256_by_arm': {p: hashlib.sha256(pathlib.Path(d).read_bytes()).hexdigest() for p,d in drivers.items()},
          'procedure_commit': os.environ.get('TRIAL_PROCEDURE_COMMIT',''),
          'library_profile_by_arm': library_profiles,
          'driver': executable, 'args': args, 'launcher_by_arm': launchers,
          'dependencies_by_arm': dependencies, 'phases': summary}
(outdir / 'summary.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record, indent=2))
PY
```

The interval describes variation among the recorded process pairs within this allocation and assumes those pairs are sufficiently comparable, rather than dominated by persistent drift. Fresh processes on one host still share its hardware and environment; the interval does not quantify differences across nodes or allocations. Inspect pair order, drift, and raw results before interpreting it. Standard deviation describes measurement spread; it is not the confidence interval or a separate count of independent samples. Follow the staged replication plan in 08; do not declare zero cost merely because an interval includes zero.

## 5. Run inside one compute allocation

Set a CPU list actually assigned to the job. `taskset` constrains execution; it does not allocate CPUs. Keep jobs sequential and avoid build jobs while timing. For the serial pilot select one allocated CPU; for threaded FFTW use a recorded set large enough for its thread count.

```bash
export CPUSET=0   # replace with a CPU assigned to this allocation
export PAIRS=10
export COMPARE=reference
unset COMPARE_EXECUTABLE
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export BLIS_NUM_THREADS=1
lscpu > "$TRIAL_ROOT/logs/execution-cpu.txt"
taskset -pc $$ >> "$TRIAL_ROOT/logs/execution-cpu.txt"
```

Run each package's timing commands first for `COMPARE=reference`. Then select an installed removal variant and a new case label or comparator directory. A positive `full_runtime_increase_percent` means full was slower than that comparator; a negative value means it was faster. All numbers are elapsed runtime changes, not throughput-loss percentages.

For an executable/consumer comparison, follow [07](07-consumer-pie.md), which compiles the same driver source with `EXE_CFLAGS` or `EXE_FFLAGS` and `EXE_LDFLAGS`, linking the same full library for the PIE-only experiment. Measure whole-process elapsed time separately from driver kernel phases. PIE removal does not change a shared library's PIC requirement. Do not feed those differently built executables to the fixed-driver comparison and call the result a library-only cost.
