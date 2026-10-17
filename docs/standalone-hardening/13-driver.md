# 13 — Automated setup, builds and individual tests

Install this driver using the [README](README.md). It needs Python 3.10 or newer and the completed private GCC 12.5 environment from 00. The source below is embedded here like the other runbook scripts; the installer copies it and the recipe snapshot into `TRIAL_ROOT/runner`.

The public commands are `setup`, `refresh-tests`, `prepare-mpi [--from-dir DIR | --check]`, `prepare-tests [--wheelhouse DIR | --check]`, `build PACKAGE [--mpi] [--retry]`, `test PACKAGE [--mpi] [--nodes N] [--ranks-per-node 1|4] [--pairs N] [--slurm-overlap]`, `status`, and `logs`. `build all` includes the three serial packages and both MPI packages. `test all` runs a sequential five-session package pilot and exports its completed timing phases to CSV. 08/10 provide the larger host/scale campaigns. Run MPI builds in a Slurm allocation because upstream correctness tests launch MPI processes.

`production` adds the [audited dense MPI workflow](README.md#after-the-pilot-run-production-density-workloads),
including sustained callers, service-core exclusions and CSV/HTML analysis.
Run `trial production --help` for its separate placement, workload and budget options.
For the next phase, use `--scope deployment --reframe`: one ordinarily compiled
caller is reused with both complete library stacks, and the existing controller
runs through ReFrame in the current allocation. `--fields`, `--fft-plan`,
`--steps` and `--checkpoint-every` define the repeated work. The default scope
remains `stack` for existing commands. See the
[next-session commands](README.md#next-session-fixed-caller-application-pattern-assessment).

The OSU follow-up uses `osu prepare [--from-dir DIR | --check]`,
`osu build [--jobs N] [--check] [--retry]`, `osu test --after-production DIR
[--reframe]` and `osu report DIR`. Prepare sources on the connected login node;
build/test never download. Callers can be built on a compute node after staging.
Complete the next deployment-scope production test before starting OSU timing.
See [12 - automated OSU](12-osu-screen.md).

`setup` generates profiles, probes C/C++/Fortran, checks emitted PIE/RELRO/NOW/non-executable-stack properties, checks mixed shared/tool linking, and generates measurement files. Every shell command runs in a separate strict Bash process; sourcing the saved environment no longer changes an interactive shell’s options. The driver prints progress every 30 seconds during long steps and the last 25 log lines on failure.

Compatibility adjustment is automatic during compiler qualification. Only a diagnostic identifying a rejected requested control, or the explicit FORTIFY implementation check, authorizes a retry with that control disabled for the affected language. PIE compile/link settings move together. A rejected negative option is also recorded. Other failures stop. Artifact checks must still pass. No security certification is implied by accepting flags.

The saved `qualification.json` contains the exact full/reference vectors and a `complete-HASH` or `compatible-HASH` identity; `policy.json` retains the diagnostics. These identities describe the trial’s effective flags. Directory names `full`/`reference` remain the requested arms. Managed build records and paired summaries preserve the effective identity, so a reduced result cannot be reported as a complete-profile measurement.

The driver uses the recipe blocks from 01–06/11, with only arm selection and matching reference caller paths changed. Keep the block order coordinated with this driver when editing recipes. Setup regenerates the timing/ReFrame/placement helpers. Build records include recipe/settings/dependency fingerprints and installed artifact hashes. An unchanged completed build is verified and skipped. Changed build inputs require a fresh root; scheduling/measurement-only edits can be regenerated without recompiling packages. Existing manual installations are retained and require a manual audit or a separate trial root before driver-managed builds.

After a failed driver build, fix the reported source/environment/site issue and repeat the same build command with `--retry`. It archives the failed build/install directories under `build/retired`, retaining their original logs, then runs configure/build/upstream tests/install/caller compilation again. It does not overwrite a completed build or infer that a numerical/test failure means a flag should be removed. Package-specific incompatibilities still need investigation; compiler rejection is handled before those builds.

`prepare-mpi` is the explicit login-node download step for UCX/Open MPI. It verifies the pinned SHA-256 values, reuses valid cached archives, and accepts downloads only after verification. Downloads use temporary filenames; invalid older archives are preserved when replaced. `--from-dir DIR` imports transferred archives without network access; `--check` verifies the local cache without mutation. Compute-node build staging only verifies and extracts local archives, using temporary extraction directories to avoid reusing interrupted extraction. Source preparation does not change build recipes or the identities of completed packages.

UCX defaults to TCP/shared-memory transport configuration. Before building UCX, an IB/RoCE site with the development dependencies can export `TRIAL_UCX_CONFIGURE_ARGS="--with-verbs --with-rdmacm"` (or explicit approved prefixes). The selected configuration enters the build fingerprint. Slurm and fabric drivers remain the site installations.

Run `prepare-tests` on a connected login/staging node before entering the test allocation. It installs pinned ReFrame 4.10.4 into the shared private venv, verifies its version/dependencies and records installed Python packages. `--wheelhouse DIR` installs from local wheels with the package index disabled. `--check` only verifies readiness and works without network access. Tests run the same readiness check and never install packages. Preparation needs `env.sh`, but does not require flag qualification or any package builds. Use a compatible Linux/Python installation available at the same absolute path on compute nodes; do not copy a virtual environment from a Mac or relocate it. MPI tests qualify placement/transport in the selected allocation first, then use matching callers/libraries/MPI/UCX per arm. Serial FFTW needs no MPI, HDF5 or LAPACK. LAPACK adds only BLAS. Test reports include individual pair data, means, standard deviations, paired effects and intervals through the existing harness.

Do not update the runner or regenerate files while a campaign is queued or running. The driver prevents overlapping driver commands in one trial root; independently submitted campaign jobs are the operator’s responsibility. A new setup does not adopt old libraries or change an earlier result’s identity.

```python
import argparse, csv, datetime, fcntl, hashlib, json, os, pathlib, re, shlex, shutil, socket, subprocess, sys, time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
RECIPES = HERE / 'recipes'
FLAGS = ('CFLAGS','CXXFLAGS','FFLAGS','FCFLAGS','CPPFLAGS','SHARED_LDFLAGS',
         'EXE_CFLAGS','EXE_CXXFLAGS','EXE_FFLAGS','EXE_LDFLAGS')
LANG = {'CFLAGS':'c','EXE_CFLAGS':'c','CXXFLAGS':'cxx','EXE_CXXFLAGS':'cxx',
        'FFLAGS':'fortran','FCFLAGS':'fortran','EXE_FFLAGS':'fortran',
        'SHARED_LDFLAGS':'link','EXE_LDFLAGS':'link','CPPFLAGS':'c'}
CONTROL = {
 'stack': ('-fstack-protector-strong','-fstack-protector-all','-fno-stack-protector'),
 'clash': ('-fstack-clash-protection','-fno-stack-clash-protection'),
 'cf': ('-fcf-protection=full','-fcf-protection=none'),
 'init': ('-ftrivial-auto-var-init=zero','-ftrivial-auto-var-init=uninitialized'),
 'fortify': ('-D_FORTIFY_SOURCE=2','-D_FORTIFY_SOURCE=3'),
 'assertions': ('-D_GLIBCXX_ASSERTIONS',),
 'relro': ('-Wl,-z,relro','-Wl,-z,norelro'),
 'now': ('-Wl,-z,now','-Wl,-z,lazy'),
 'pie': ('-fPIE','-fno-pie','-pie','-no-pie')}
# Removing a rejected positive option uses the explicit negative where accepted.
NEGATIVE = {'stack':'-fno-stack-protector','clash':'-fno-stack-clash-protection',
 'cf':'-fcf-protection=none','init':'-ftrivial-auto-var-init=uninitialized',
 'relro':'-Wl,-z,norelro','now':'-Wl,-z,lazy'}
BUILDS = {'fftw':('02-fftw',0,'FFTW_VARIANTS'), 'hdf5':('03-hdf5',0,'HDF5_VARIANTS'),
 'blas':('04-lapack',0,'BLAS_VARIANTS'), 'lapack':('04-lapack',1,'LAPACK_VARIANTS'),
 'ucx':('00b-openmpi-ucx',3,'MPI_VARIANTS'), 'openmpi':('00b-openmpi-ucx',4,'MPI_VARIANTS'),
 'fftw-mpi':('05-parallel',1,'FFTW_MPI_VARIANTS'), 'hdf5-mpi':('05-parallel',4,'HDF5_MPI_VARIANTS')}
CALLERS = {'fftw':('02-fftw',1), 'hdf5':('03-hdf5',1), 'lapack':('04-lapack',2),
           'fftw-mpi':('05-parallel',2),'hdf5-mpi':('05-parallel',5)}
DEPS = {'lapack':['blas'],'openmpi':['ucx'],'fftw-mpi':['openmpi'],'hdf5-mpi':['openmpi']}
WORKLOADS = {'fftw':'fft-small,fft-large,fft-plan,fft-startup',
 'hdf5':'hdf5-contiguous,hdf5-chunked,hdf5-startup','lapack':'lapack-small,lapack-large,lapack-startup',
 'fftw-mpi':'fft-mpi-small,fft-mpi,fft-mpi-plan','hdf5-mpi':'hdf5-collective,hdf5-independent,hdf5-mpi-small'}

def read(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default

def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(obj, indent=2)+'\n'); temp.replace(path)

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()

def filehash(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024), b''): h.update(chunk)
    return h.hexdigest()

def block(name, index):
    return re.findall(r'```bash\n(.*?)\n```', (RECIPES/(name+'.md')).read_text(), re.S)[index]+'\n'

def effective():
    policy = read(HERE/'policy.json', {'disabled':{}})
    values = {}
    for name in FLAGS:
        tokens = shlex.split(os.environ.get(name,''))
        for group, rejected in policy['disabled'].get(LANG[name],{}).items():
            if not any(t in CONTROL[group] for t in tokens): continue
            tokens = [t for t in tokens if t not in CONTROL[group]]
            replacement = NEGATIVE.get(group)
            if group == 'pie': replacement = '-no-pie' if LANG[name]=='link' else '-fno-pie'
            if replacement and replacement not in rejected: tokens.append(replacement)
        values[name] = ' '.join(tokens)
    return values

def header(profiles=True):
    text = 'set -euo pipefail\nsource "$TRIAL_ROOT/env.sh"\n'
    if profiles: text += 'source "$TRIAL_ROOT/profiles.sh"\n'
    return text

def ucx_configure_args():
    config = read(HERE/'mpi-config.json', {})
    saved = config.get('ucx_configure_args')
    override = os.environ.get('TRIAL_UCX_CONFIGURE_ARGS')
    args = saved if saved is not None else shlex.split(override or '--without-verbs --without-rdmacm')
    if saved is not None and override is not None and shlex.split(override) != saved:
        raise RuntimeError('TRIAL_UCX_CONFIGURE_ARGS conflicts with runner/mpi-config.json. Keep the recorded build selection.')
    allowed = ('--with-verbs','--without-verbs','--with-rdmacm','--without-rdmacm')
    if not isinstance(args,list) or not args or any(not isinstance(a,str) or
        (a not in allowed and not a.startswith(('--with-verbs=','--with-rdmacm='))) for a in args):
        raise RuntimeError('UCX configure arguments must contain only verbs/rdmacm options and explicit prefixes.')
    return args

def with_mpi_tuning(text):
    # Apply runtime choices after activation clears inherited UCX variables.
    pattern = r'(?m)^([ \t]*)(activate_mpi_profile [^\n]+|source "\$TRIAL_ROOT/mpi-env(?:-reference)?\.sh")[ \t]*$'
    return re.sub(pattern, lambda m: m[0]+'\n'+m[1]+
        'if test -n "${TRIAL_MPI_TUNING:-}"; then source "$TRIAL_MPI_TUNING"; fi\n'+m[1]+
        # UCX_PREFIX is a shell path, not a UCX setting. Its unused-variable
        # warning contaminates ph5diff output compared against golden files.
        'export -n UCX_PREFIX\n'+m[1]+
        'if test "${TRIAL_SLURM_OVERLAP:-0}" = 1; then\n'+m[1]+
        '  case " ${OMPI_MCA_plm_slurm_args:-} " in *" --overlap "*) ;;\n'+m[1]+
        '    *) export OMPI_MCA_plm_slurm_args="${OMPI_MCA_plm_slurm_args:+$OMPI_MCA_plm_slurm_args }--overlap" ;; esac\n'+m[1]+
        'fi', text)

def verify_ucx_rdma(prefix):
    code = 'export LD_LIBRARY_PATH='+shlex.quote(str(prefix/'lib'))+':"$GCC_LIB_DIRS${TRIAL_SITE_LIB_DIRS:+:$TRIAL_SITE_LIB_DIRS}"\n'
    code += shlex.quote(str(prefix/'bin/ucx_info'))+' -d\n'
    output = shell('ucx-rdma-capability', code, profiles=False, capture=True)
    if not re.search(r'^\s*#\s*Transport:\s*rc_(?:mlx5|verbs)\b',output,re.M):
        raise RuntimeError('Requested RDMA UCX has no available RC transport in this allocation. Check verbs support, drivers and active ports; no TCP fallback is accepted.')
    return output

def environment():
    env = os.environ.copy()
    env['TRIAL_PROCEDURE_COMMIT'] = (HERE/'procedure.txt').read_text().strip() if (HERE/'procedure.txt').exists() else 'unrecorded'
    env.update(TRIAL_ROOT=str(ROOT), TRIAL_DRIVER_SCRIPT=str(HERE/'trial.py'),
               TRIAL_DRIVER_PYTHON=sys.executable, TRIAL_COMPONENT_ID='global')
    tuning = read(HERE/'mpi-config.json', {}).get('tuning_file')
    if tuning:
        if env.get('TRIAL_MPI_TUNING',tuning) != tuning:
            raise RuntimeError('TRIAL_MPI_TUNING conflicts with the recorded MPI selection. Use its saved site runtime file.')
        env['TRIAL_MPI_TUNING'] = tuning
    return env

def shell(task, text, *, profiles=True, capture=False, extra=None):
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    script = HERE/'jobs'/f'{task}-{stamp}.sh'
    script.parent.mkdir(exist_ok=True)
    script.write_text(header(profiles)+with_mpi_tuning(text))
    log = ROOT/'logs'/'runner'/f'{task}-{stamp}.log'
    log.parent.mkdir(parents=True, exist_ok=True)
    env = environment(); env.update(extra or {})
    print(f'{task}: running; log {log}', flush=True)
    with log.open('w') as out:
        proc = subprocess.Popen(['bash',str(script)], env=env, stdout=out, stderr=subprocess.STDOUT)
        while True:
            try: code = proc.wait(timeout=30); break
            except subprocess.TimeoutExpired: print(f'{task}: still running; log {log}', flush=True)
    if code:
        tail = '\n'.join(log.read_text(errors='replace').splitlines()[-25:])
        raise RuntimeError(f'{task} failed (exit {code}).\n{tail}\nFull log: {log}\nYour calling shell is still usable.')
    print(f'{task}: PASS', flush=True)
    return log.read_text() if capture else log

def get_flags(profile):
    # Last line isolates the JSON from site module messages.
    code = 'source "$TRIAL_ROOT/env.sh"\nsource "$TRIAL_ROOT/profiles.sh"\nprofile_flags '+profile+'\n'
    code += shlex.quote(sys.executable)+' -c '+shlex.quote('import json,os;print(json.dumps({k:os.environ[k] for k in '+repr(FLAGS)+'}))')
    result = subprocess.run(['bash','-euc',code], env=environment(), capture_output=True, text=True)
    if result.returncode: raise RuntimeError(result.stderr or result.stdout)
    return json.loads(result.stdout.splitlines()[-1])

def qualify():
    # Probe complete vectors in each language; retry only named rejected controls.
    policy = read(HERE/'policy.json', {'disabled':{},'events':[]})
    starting_policy = digest(policy)
    save(HERE/'policy.json', policy)
    probes = ROOT/'bench/probes'; probes.mkdir(parents=True,exist_ok=True)
    c = '#include <stdio.h>\n#include <string.h>\n#if defined(_FORTIFY_SOURCE) && __USE_FORTIFY_LEVEL != _FORTIFY_SOURCE\n#error Requested FORTIFY level is not implemented\n#endif\nint main(void){char b[64];snprintf(b,sizeof b,"probe");return puts(b)<0;}\n'
    (probes/'probe.c').write_text(c); (probes/'probe.cc').write_text(c)
    (probes/'probe.f90').write_text('program probe\n print *, "probe"\nend program\n')
    for profile in ('full','reference'):
        for lang, compiler, flagname, suffix in [('c','CC','EXE_CFLAGS','c'),('cxx','CXX','EXE_CXXFLAGS','cc'),('fortran','FC','EXE_FFLAGS','f90')]:
            for attempt in range(32):
                values = get_flags(profile)
                log = probes/f'{profile}-{lang}-{attempt}.log'
                command = f'profile_flags {profile}\nread -r -a args <<< "${flagname}"\nread -r -a ldargs <<< "$EXE_LDFLAGS"\n'
                command += f'"${compiler}" -Werror "${{args[@]}}" "$TRIAL_ROOT/bench/probes/probe.{suffix}" "${{ldargs[@]}}" -o "$TRIAL_ROOT/bench/probes/{lang}-{profile}"\n'
                proc = subprocess.run(['bash','-c',header()+command],env=environment(),capture_output=True,text=True)
                output = proc.stdout+proc.stderr; log.write_text(output)
                if proc.returncode == 0: break
                match = None
                for line in output.splitlines():
                    if not re.search(r'unrecognized (command.line )?option|unknown (argument|option)|unsupported option|not supported', line, re.I): continue
                    for group, tokens in CONTROL.items():
                        for token in tokens:
                            if token in line and token in shlex.split(values[flagname]+' '+values['EXE_LDFLAGS']):
                                match = (group,token,'link' if token in shlex.split(values['EXE_LDFLAGS']) else lang)
                if 'Requested FORTIFY level is not implemented' in output:
                    match = ('fortify', next(t for t in shlex.split(values[flagname]) if t.startswith('-D_FORTIFY_SOURCE=')), lang)
                if not match: raise RuntimeError(f'Flag probe failed; no confirmed unsupported control. Read {log}\n{output[-2500:]}')
                group, token, lane = match
                rejected = policy['disabled'].setdefault(lane,{}).setdefault(group,[])
                if token in rejected: raise RuntimeError(f'Compatibility retry made no progress; read {log}')
                rejected.append(token)
                if group == 'pie':
                    # PIE compilation/linking are a single executable treatment.
                    for target in ('c','cxx','fortran','link'):
                        policy['disabled'].setdefault(target,{}).setdefault(group,[])
                policy['events'].append({'language':lane,'control':group,'rejected':token,'log':str(log),'diagnostic':output})
                save(HERE/'policy.json',policy)
                print(f'ADJUSTED: {lane} {group}; rejected {token}. Recorded in runner/policy.json; retrying.',flush=True)
            else: raise RuntimeError('Too many compatibility retries')
            shell(f'probe-{profile}-{lang}', f'"$TRIAL_ROOT/bench/probes/{lang}-{profile}"\n')
    if digest(policy) != starting_policy:
        print('Rechecking all languages with the final compatibility policy.',flush=True)
        return qualify()
    # Keep mixed executable/shared linking qualification from the canonical recipe.
    shell('mixed-links',block('01-common',2))
    # Verify emitted ELF properties against the effective vectors, not just acceptance.
    for profile in ('full','reference'):
        values = get_flags(profile)
        for kind in ('c','cxx','fortran'):
            path = probes/f'{kind}-{profile}'
            # The Fortran probe executable uses its language name.
            elf = subprocess.check_output(['readelf','-hW',str(path)],text=True)
            seg = subprocess.check_output(['readelf','-lW',str(path)],text=True)
            dyn = subprocess.check_output(['readelf','-dW',str(path)],text=True)
            pie = '-pie' in shlex.split(values['EXE_LDFLAGS'])
            if not re.search(r'Type:\s+'+('DYN' if pie else 'EXEC'),elf):
                raise RuntimeError(f'{path}: unexpected ELF type')
            if ('GNU_RELRO' in seg) != ('-Wl,-z,relro' in shlex.split(values['EXE_LDFLAGS'])):
                raise RuntimeError(f'{path}: RELRO does not match effective flags')
            if bool(re.search(r'BIND_NOW|Flags:.*NOW',dyn)) != ('-Wl,-z,now' in shlex.split(values['EXE_LDFLAGS'])):
                raise RuntimeError(f'{path}: NOW does not match effective flags')
            stack = next((line for line in seg.splitlines() if 'GNU_STACK' in line),'')
            if not stack or re.search(r'\bRW?E\b',stack): raise RuntimeError(f'{path}: executable or missing GNU_STACK')
    values = {p:get_flags(p) for p in ('full','reference')}
    identity = ('compatible-' if policy['disabled'] else 'complete-')+digest(values)[:12]
    save(HERE/'qualification.json', {'identity':identity,'policy':policy,'flags':values})
    print(f'Qualified {identity}. Fortran FORTIFY: not applicable. Exact flags: runner/qualification.json')

def setup():
    if not (ROOT/'env.sh').exists(): raise RuntimeError('Finish GCC bootstrap 00 through env.sh first.')
    # Existing generated activation files used to enable errexit in the caller.
    path = ROOT/'env.sh'; original = path.read_text()
    fixed = re.sub(r'^set -euo pipefail\n','',original,flags=re.M)
    if original != fixed:
        shutil.copy2(path, HERE/'env-before-shell-fix.sh'); path.write_text(fixed)
    for name in ('bench','logs','build','install','src','tools','results','reframe'): (ROOT/name).mkdir(exist_ok=True)
    shell('compiler-check', 'for compiler in "$CC" "$CXX" "$FC"; do test "$("$compiler" -dumpfullversion)" = 12.5.0; "$compiler" --version; done\n', profiles=False)
    new_profile = block('01-common',0)
    if (HERE/'setup.json').exists() and list((HERE/'state').glob('*.json')):
        old = read(HERE/'setup.json')
        if old['profile_recipe'] != digest(new_profile):
            raise RuntimeError('Profile recipe changed after builds. Use a fresh trial root; existing binaries keep their identity.')
    shell('profiles',new_profile,profiles=False)
    previous = read(HERE/'qualification.json')
    qualify()
    if previous and previous != read(HERE/'qualification.json') and list((HERE/'state').glob('*.json')):
        raise RuntimeError('Effective flags changed after builds. Use a fresh trial root; do not time old builds under the new profile.')
    generate_measurements()
    save(HERE/'setup.json',{'profile_recipe':digest(new_profile),'measurement_recipes':measurement_hash(),'qualification':read(HERE/'qualification.json'),
                           'env':filehash(ROOT/'env.sh'),'site_env':filehash(ROOT/'site-env.sh') if (ROOT/'site-env.sh').exists() else None})
    print('Setup complete. Next: trial build fftw, trial build fftw --mpi, or trial build all.')

def measurement_hash():
    return digest([block('01-common',4),block('06-reframe',1),block('06-reframe',2),block('11-stack-comparison',2),block('00b-openmpi-ucx',5)])

def generate_measurements():
    generation = block('01-common',4)+block('00b-openmpi-ucx',5).split('export TRIAL_EXPECTED_NODES=2')[0]
    generation += block('06-reframe',1)+block('06-reframe',2)+block('11-stack-comparison',2)
    shell('measurement-files',generation)

def refresh_tests():
    state = require_setup(check_measurements=False)
    if state['qualification'] != read(HERE/'qualification.json'):
        raise RuntimeError('Recorded qualification changed; do not refresh measurements over mismatched builds.')
    generate_measurements()
    state['measurement_recipes'] = measurement_hash()
    save(HERE/'setup.json',state)
    print('Measurement scripts refreshed; compiler qualification and package builds retained.')

def require_setup(check_measurements=True):
    state = read(HERE/'setup.json')
    if not state: raise RuntimeError('Run trial setup first.')
    if state['qualification']['policy'] != read(HERE/'policy.json', {'disabled':{},'events':[]}):
        raise RuntimeError('Compatibility policy changed. Run trial setup before continuing.')
    current = filehash(ROOT/'site-env.sh') if (ROOT/'site-env.sh').exists() else None
    if state['env'] != filehash(ROOT/'env.sh') or state['site_env'] != current:
        raise RuntimeError('env.sh/site-env.sh changed since qualification. Run trial setup before continuing.')
    if state['profile_recipe'] != digest(block('01-common',0)):
        raise RuntimeError('Updated profile recipe requires trial setup.')
    if check_measurements and state['measurement_recipes'] != measurement_hash():
        raise RuntimeError('Measurement recipes changed. Run trial refresh-tests to refresh measurement scripts without rebuilding packages.')
    return state

def paths(package, arm):
    suffix = 'reference' if arm=='reference' else 'fixed'
    if package in ('ucx','openmpi'):
        name = 'ucx-1.16.0-' if package=='ucx' else 'openmpi-4.1.8-ucx-'
        return ROOT/'build'/f'{package}-{suffix}', ROOT/'install'/(name+suffix)
    return ROOT/'build'/f'{package}-{arm}', ROOT/'install'/package/arm

def inventory(path):
    return {str(p.relative_to(ROOT)):filehash(p) for p in sorted(path.rglob('*')) if p.is_file()}

def verify_state(name):
    state = read(HERE/'state'/f'{name}.json')
    if not state: raise RuntimeError(f'{name} is not completed by this driver. Run trial build for that package.')
    for path, expected in state['artifacts'].items():
        p = ROOT/path
        if not p.is_file() or filehash(p)!=expected: raise RuntimeError(f'Artifact changed or missing: {p}')
    return state

def mpi_sources():
    # Keep the pinned URLs/checksums in one place: the MPI source recipe.
    recipe = block('00b-openmpi-ucx',1)
    urls = dict(re.findall(r'curl -fL --retry 3 -o (\S+) \\\n\s*(https://\S+)',recipe))
    sums = re.findall(r'^([0-9a-f]{64})  (\S+)$',recipe,re.M)
    if set(urls) != {'openmpi-4.1.8.tar.bz2','ucx-1.16.0.tar.gz'} or len(sums)!=2:
        raise RuntimeError('MPI source recipe changed; update the driver source parser together with the recipe.')
    if {name for sha,name in sums} != set(urls): raise RuntimeError('MPI URL/checksum names differ.')
    return [{'archive':name,'sha256':sha,'url':urls[name],'directory':name.split('.tar.')[0]} for sha,name in sums]

def verify_mpi_archives():
    problems = []
    for source in mpi_sources():
        archive = ROOT/'downloads'/source['archive']
        if not archive.is_file(): problems.append(f'Missing {archive}')
        elif filehash(archive) != source['sha256']: problems.append(f'SHA-256 mismatch: {archive}')
    if problems:
        raise RuntimeError('\n'.join(problems)+'\nRun trial prepare-mpi on a connected login node, or trial prepare-mpi --from-dir DIR with transferred archives. Compute builds never download MPI sources.')

def prepare_mpi(args):
    if args.check:
        verify_mpi_archives()
        print('MPI/UCX archives are present and SHA-256 verified; no download or extraction performed.')
        return
    origin = pathlib.Path(args.from_dir).expanduser().resolve() if args.from_dir else None
    if origin and not origin.is_dir(): raise RuntimeError(f'Missing source archive directory: {origin}')
    downloads = ROOT/'downloads'; downloads.mkdir(parents=True,exist_ok=True)
    for source in mpi_sources():
        dest = downloads/source['archive']
        if dest.is_file() and filehash(dest)==source['sha256']:
            print(f'{source["archive"]}: already verified; reused')
            continue
        temp = downloads/(source['archive']+'.part-'+str(time.time_ns()))
        if origin:
            incoming = origin/source['archive']
            if not incoming.is_file() or filehash(incoming)!=source['sha256']:
                raise RuntimeError(f'Missing or wrong SHA-256: {incoming}. No download attempted.')
            shutil.copy2(incoming,temp)
        else:
            command = shlex.join(['curl','-fL','--retry','3','-o',str(temp),source['url']])+'\n'
            try: shell('download-'+source['directory'],command,profiles=False)
            except RuntimeError as error:
                raise RuntimeError(f'{error}\nPrepare sources on a connected login/staging node, then use --from-dir DIR if transfer is needed. Any partial download remains at {temp}; it is never used by the build.') from None
        if filehash(temp)!=source['sha256']:
            raise RuntimeError(f'SHA-256 mismatch: {temp}. Download retained for inspection; not accepted as a source archive.')
        if dest.exists():
            rejected = downloads/(dest.name+'.rejected-'+str(time.time_ns()))
            dest.rename(rejected)
            print(f'Preserved invalid previous archive: {rejected}')
        temp.replace(dest)
        print(f'{source["archive"]}: SHA-256 verified')
    verify_mpi_archives()
    sums = ''.join(f'{source["sha256"]}  {source["archive"]}\n' for source in mpi_sources())
    (downloads/'MPI-SHA256SUMS').write_text(sums)
    print('MPI/UCX sources prepared. Resume trial build all --retry on the compute node; completed builds are reused.')

def stage_mpi():
    # This is called by builds and must never access a source URL.
    verify_mpi_archives()
    src = ROOT/'src'; src.mkdir(parents=True,exist_ok=True)
    for source in mpi_sources():
        dest = src/source['directory']
        entry = 'contrib/configure-release' if source['directory'].startswith('ucx-') else 'configure'
        if dest.exists():
            if not (dest/entry).is_file():
                raise RuntimeError(f'Incomplete existing source tree: {dest}. Preserve it outside src, then rerun the build to extract the verified local archive.')
            continue
        # Extract into a temporary directory so interruption cannot create a
        # final-looking partial source tree. Failed extraction is retained.
        staging = src/('.mpi-extract-'+str(time.time_ns())); staging.mkdir()
        command = shlex.join(['tar','-xf',str(ROOT/'downloads'/source['archive']),'-C',str(staging)])+'\n'
        shell('extract-'+source['directory'],command)
        extracted = staging/source['directory']
        if not (extracted/entry).is_file(): raise RuntimeError(f'Archive has no expected configure entry point: {extracted/entry}')
        extracted.rename(dest)
        staging.rmdir()


def build_one(package, arm, retry=False):
    for dep in DEPS.get(package,[]): build_one(dep,arm,retry)
    name = f'{package}-{arm}'
    doc, index, array = BUILDS[package]
    recipe = block(doc,index)
    recipe = re.sub(array+r'=\(full reference\)',f'{array}=({arm})',recipe)
    if package=='openmpi': recipe = recipe.removesuffix('source "$TRIAL_ROOT/mpi-env.sh"\n')
    recipe = f'{array}=({arm})\nLAPACK_SOURCE="$TRIAL_ROOT/src/lapack-3.12.1"\n'+recipe
    if package=='ucx':
        args = ucx_configure_args()
        recipe = 'UCX_TRANSPORT_ARGS=('+shlex.join(args)+')\n'+recipe
    caller = ''
    if package in CALLERS:
        caller = block(*CALLERS[package])
        if arm=='reference':
            caller = caller.replace('activate_mpi_profile full','activate_mpi_profile reference').replace('profile_flags full','profile_flags reference').replace(f'install/{package}/full',f'install/{package}/reference')
            caller = caller.replace('install/blas/full','install/blas/reference').replace(f'bench/{package}-fixed',f'bench/{package}-reference')
        if package.endswith('-mpi'): caller = f'activate_mpi_profile {arm}\n'+caller
    deps = {d:read(HERE/'state'/f'{d}-{arm}.json')['identity'] for d in DEPS.get(package,[])}
    identity = digest({'recipe':recipe,'caller':caller,'deps':deps,'setup':{k:v for k,v in require_setup().items() if k!='measurement_recipes'}})
    statefile = HERE/'state'/f'{name}.json'
    if statefile.exists():
        state = verify_state(name)
        if state['identity'] != identity: raise RuntimeError(f'{name}: inputs changed. Preserve this trial and build in a fresh root.')
        print(f'{name}: already complete; verified artifacts'); return
    build, prefix = paths(package,arm)
    pending = HERE/'pending'/f'{name}.json'
    if build.exists() or prefix.exists():
        if not retry or not pending.exists():
            raise RuntimeError(f'{name}: existing directories retained. For a failed driver build, rerun with --retry; manual installations require audit or a fresh trial root.')
        stamp = str(time.time_ns()); retired = ROOT/'build'/'retired'/f'{name}-{stamp}'; retired.mkdir(parents=True)
        for path in (build,prefix):
            if path.exists(): shutil.move(str(path),str(retired/path.parent.name))
        oldlogs = ROOT/'logs'/(f'{package}-'+('reference' if arm=='reference' else 'fixed')) if package in ('ucx','openmpi') else ROOT/'logs'/package/arm
        if oldlogs.exists(): shutil.move(str(oldlogs),str(retired/'logs'))
        print(f'{name}: preserved failed attempt at {retired}')
    if package in ('ucx','openmpi'): stage_mpi()
    save(pending,{'identity':identity})
    shell(name,recipe+caller)
    artifacts = inventory(prefix)
    if not artifacts: raise RuntimeError(f'{name}: no installed artifacts')
    if package=='ucx' and any(a=='--with-verbs' or a.startswith('--with-verbs=') for a in ucx_configure_args()):
        evidence = verify_ucx_rdma(prefix)
        (ROOT/'logs'/('ucx-fixed' if arm=='full' else 'ucx-reference')/'rdma-capability.txt').write_text(evidence)
    if caller:
        binary = ROOT/'bench'/f'{package}-{"reference" if arm=="reference" else "fixed"}'
        artifacts[str(binary.relative_to(ROOT))] = filehash(binary)
    if package=='openmpi':
        envfile = ROOT/('mpi-env-reference.sh' if arm=='reference' else 'mpi-env.sh')
        artifacts[str(envfile.relative_to(ROOT))] = filehash(envfile)
    save(statefile,{'identity':identity,'package':package,'arm':arm,'effective_profile':read(HERE/'qualification.json'),
                    'artifacts':artifacts,'dependencies':deps})
    pending.unlink()

def selected(package, mpi):
    if package=='all': return ['fftw','hdf5','lapack','fftw-mpi','hdf5-mpi']
    if mpi and package=='lapack': raise RuntimeError('This LAPACK trial is serial; it has no MPI variant.')
    return [package]+([package+'-mpi'] if mpi else [])

def check_reframe():
    reframe = ROOT/'tools/reframe-venv/bin/reframe'
    python = ROOT/'tools/reframe-venv/bin/python'
    action = 'Run trial prepare-tests on a login/staging node first, or use --wheelhouse DIR for local wheels.'
    if not reframe.is_file() or not python.is_file():
        raise RuntimeError('ReFrame is not prepared. '+action+' Test commands do not install packages.')
    code = f'test "$("{reframe}" --version)" = 4.10.4\n'
    code += f'"{python}" -m pip check\n'
    try: shell('check-reframe', code, profiles=False, extra={'PIP_DISABLE_PIP_VERSION_CHECK':'1'})
    except RuntimeError as error: raise RuntimeError(f'{error}\nReFrame readiness check failed. {action}') from None
    return reframe

def prepare_tests(args):
    if not (ROOT/'env.sh').is_file(): raise RuntimeError('Finish bootstrap through env.sh before preparing ReFrame.')
    if args.check:
        check_reframe()
        print('ReFrame 4.10.4 is ready here; no packages installed and no index access requested.')
        return
    extra = {'PIP_DISABLE_PIP_VERSION_CHECK':'1'}
    if args.wheelhouse:
        wheels = pathlib.Path(args.wheelhouse).expanduser().resolve()
        if not wheels.is_dir(): raise RuntimeError(f'Missing local wheelhouse: {wheels}')
        extra.update(PIP_NO_INDEX='1', PIP_FIND_LINKS=str(wheels), PIP_CONFIG_FILE=os.devnull)
    # Preparation is explicit. Tests never call this install recipe.
    shell('prepare-reframe', block('06-reframe',0).replace('python3 -m venv',shlex.quote(sys.executable)+' -m venv'),
          profiles=False, extra=extra)
    check_reframe()
    shell('record-reframe', '"$TRIAL_ROOT/tools/reframe-venv/bin/python" -m pip freeze > "$TRIAL_ROOT/tools/reframe-venv/installed.txt"\n'
          '"$TRIAL_ROOT/tools/reframe-venv/bin/python" --version\n',
          profiles=False, extra={'PIP_DISABLE_PIP_VERSION_CHECK':'1'})
    print('ReFrame prepared. On the compute node run trial prepare-tests --check, then trial test PACKAGE. No payload rebuild is needed.')

def verify_test_tree(package, arm):
    for dep in DEPS.get(package,[]): verify_test_tree(dep,arm)
    state = verify_state(f'{package}-{arm}')
    if state['effective_profile'] != read(HERE/'qualification.json'):
        raise RuntimeError('Qualification differs from installed artifacts; use a fresh root.')

def test_one(args, record=None):
    require_setup()
    if not os.environ.get('SLURM_JOB_ID'): raise RuntimeError('Run tests inside a Slurm allocation on compute nodes. See README salloc/srun example.')
    reframe = check_reframe()
    packages = selected(args.package,args.mpi)
    if args.mpi and args.package!='all': packages = [args.package+'-mpi']
    package = packages[0]
    for arm in ('full','reference'): verify_test_tree(package,arm)
    run = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out = ROOT/'results/reframe'/run; out.mkdir(parents=True)
    if record is not None: record['result_dir'] = str(out.relative_to(ROOT))
    io = os.environ.get('IO_DIR')
    if package.startswith('hdf5') and not io: raise RuntimeError('Set IO_DIR to a dedicated trial directory on the filesystem you want to measure.')
    io = io or str(ROOT/'results/io'); pathlib.Path(io).mkdir(parents=True,exist_ok=True)
    extra = {'RUN_ID':run,'IO_DIR':io,'WORKLOADS':WORKLOADS[package],'COMPARATORS':'reference','TRIAL_SCOPE':'stack','PAIRS':str(args.pairs),
             'CPUSET':os.environ.get('CPUSET',str(min(os.sched_getaffinity(0)))),'TRIAL_ALLOCATION_MODE':'individual','TRIAL_REPEAT_SCOPE':'allocation',
             'TRIAL_SLURM_OVERLAP':'1' if getattr(args,'slurm_overlap',False) else '0'}
    if not args.mpi: extra.update(TRIAL_SELECTED_HOSTS=socket.gethostname(),TRIAL_EXPECTED_NODES='1')
    code = ''
    if args.mpi:
        hosts = subprocess.check_output(['scontrol','show','hostnames',os.environ['SLURM_JOB_NODELIST']],text=True).split()
        if args.nodes>len(hosts): raise RuntimeError(f'Requested {args.nodes} nodes; allocation has {len(hosts)}.')
        chosen = ','.join(hosts[:args.nodes])
        rpn = getattr(args,'ranks_per_node',1)
        slots = ','.join(f'{host}:{rpn}' for host in hosts[:args.nodes])
        extra.update(TRIAL_SELECTED_HOSTS=chosen,TRIAL_EXPECTED_NODES=str(args.nodes),RANKS_PER_NODE=str(rpn),MPI_NP=str(args.nodes*rpn),
                     MPI_MAP=f'ppr:{rpn}:node',TRIAL_MPI_HOST_SLOTS=slots,MPI_EXTRA_ARGS='--host '+slots+' --nooversubscribe')
        smoke = block('00b-openmpi-ucx',5).split('export TRIAL_EXPECTED_NODES=2 RANKS_PER_NODE=1\n')[1]
        smoke = smoke.replace('-np 2','-np "$MPI_NP" --host "$TRIAL_MPI_HOST_SLOTS" --nooversubscribe')
        smoke = smoke.replace('--map-by ppr:1:node','--map-by "$MPI_MAP"').replace("--mca btl '^uct'",'--mca btl "${OMPI_MCA_btl:-^uct}"')
        shell('mpi-placement',smoke,extra=extra)
        code += 'source "$TRIAL_ROOT/mpi-env.sh"\n'
    code += f'test "$("{reframe}" --version)" = 4.10.4\n'
    code += 'export PATH="$TRIAL_ROOT/tools/reframe-venv/bin:$PATH"\n'
    code += f'"{reframe}" -C "$TRIAL_ROOT/reframe/settings.py" -c "$TRIAL_ROOT/reframe/hardening.py" -r --exec-policy=serial --performance-report --prefix="{out}/rfm" --report-file="{out}/report.json"\n'
    code = code.replace('export PATH="$TRIAL_ROOT/tools/reframe-venv/bin:$PATH"',
                        'unset UCX_LOG_LEVEL\nexport PATH="$TRIAL_ROOT/tools/reframe-venv/bin:$PATH"')
    log = shell('reframe-'+package,code,extra=extra)
    shutil.copy2(log,out/'console.log')
    print(log.read_text()); print(f'Results: {out}\nTen pairs are a pilot; use 20 pairs and repeat in three allocations for the initial assessment.')
    return out

def collect_pilot(out, manifest):
    fields = ['package','workload','phase','primary','scope','comparator','nodes','ranks_per_node','pairs',
              'full_mean_seconds','full_stdev_seconds','reference_mean_seconds','reference_stdev_seconds',
              'runtime_increase_percent','interval_low_percent','interval_high_percent','effective_profile_ids','summary']
    rows = []; missing = []
    for entry in manifest['runs']:
        found = set()
        if entry.get('result_dir'):
            for path in sorted((ROOT/entry['result_dir']).glob('paired/*/*/*/summary.json')):
                try:
                    value = read(path); workload = value['case']
                    if workload not in entry['expected_workloads'] or value['scope']!='stack' or value['comparator']!='reference':
                        raise ValueError('Unexpected pilot summary scope or workload')
                    pending = []
                    for phase, metrics in value['phases'].items():
                        interval = metrics['bootstrap_95_percent_interval']
                        pending.append(dict(zip(fields,[entry['package'],workload,phase,phase==value.get('primary_phase'),
                            value['scope'],value['comparator'],entry['nodes'],entry['ranks_per_node'],metrics['pairs'],
                            metrics['full_runtime_seconds_mean'],metrics['full_runtime_seconds_stdev'],
                            metrics['comparator_runtime_seconds_mean'],metrics['comparator_runtime_seconds_stdev'],
                            metrics['full_runtime_increase_percent'],interval[0],interval[1],
                            ';'.join(value.get('effective_profile_ids',[])),str(path.relative_to(ROOT))])))
                    if not pending or not any(row['primary'] for row in pending): raise ValueError('Missing primary phase')
                    rows.extend(pending); found.add(workload)
                except (OSError,ValueError,KeyError,TypeError,IndexError):
                    entry.setdefault('invalid_summary_files',[]).append(str(path.relative_to(ROOT)))
        entry['missing_workloads'] = sorted(set(entry['expected_workloads'])-found)
        missing.extend(entry['package']+':'+name for name in entry['missing_workloads'])
    with (out/'phases.csv').open('w',newline='') as stream:
        writer = csv.DictWriter(stream,fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    manifest['coverage_complete'] = not missing
    if missing and manifest['status']=='finished': manifest['status']='coverage_incomplete'
    manifest['completed_phase_rows'] = len(rows)
    save(out/'pilot.json',manifest)
    print('Package pilot: primary paired runtime changes (positive = full slower)',flush=True)
    for row in rows:
        if row['primary']:
            print(f"{row['package']:10} {row['workload']:20} {row['runtime_increase_percent']:+.3f}% "
                  f"[{row['interval_low_percent']:+.3f}, {row['interval_high_percent']:+.3f}]",flush=True)
    print(f'Pilot results: {out}\nCSV: {out/"phases.csv"}\nCoverage complete: {not missing}',flush=True)
    return not missing

def test(args):
    if args.package != 'all': return test_one(args)
    require_setup()
    if not os.environ.get('SLURM_JOB_ID'): raise RuntimeError('Run the package pilot in the existing compute allocation.')
    if not os.environ.get('IO_DIR'): raise RuntimeError('Set IO_DIR to a dedicated shared measurement directory before test all.')
    io = pathlib.Path(os.environ['IO_DIR'])
    if not io.is_absolute(): raise RuntimeError('IO_DIR must be an absolute shared measurement directory.')
    io.mkdir(parents=True,exist_ok=True)
    hosts = subprocess.check_output(['scontrol','show','hostnames',os.environ['SLURM_JOB_NODELIST']],text=True).split()
    if args.nodes > len(hosts): raise RuntimeError('Requested MPI node count exceeds this allocation.')
    check_reframe()
    for package in ('fftw','hdf5','lapack','fftw-mpi','hdf5-mpi'):
        for arm in ('full','reference'): verify_test_tree(package,arm)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out = ROOT/'results/pilots'/stamp; out.mkdir(parents=True)
    manifest = {'status':'running','pairs':args.pairs,'procedure_commit':(HERE/'procedure.txt').read_text().strip() if (HERE/'procedure.txt').exists() else 'unrecorded',
                'scope':'stack','slurm_overlap_requested':getattr(args,'slurm_overlap',False),'runs':[]}
    for package, mpi in (('fftw',False),('hdf5',False),('lapack',False),('fftw',True),('hdf5',True)):
        name = package+('-mpi' if mpi else '')
        manifest['runs'].append({'package':name,'argument_package':package,'mpi':mpi,'status':'pending',
            'nodes':args.nodes if mpi else 1,'ranks_per_node':getattr(args,'ranks_per_node',1) if mpi else 0,
            'expected_workloads':WORKLOADS[name].split(',')})
    save(out/'pilot.json',manifest)
    print(f'Package pilot plan: {out/"pilot.json"}',flush=True)
    try:
        for entry in manifest['runs']:
            entry['status'] = 'running'; save(out/'pilot.json',manifest)
            selected_args = argparse.Namespace(**vars(args))
            selected_args.package = entry['argument_package']; selected_args.mpi = entry['mpi']
            started = time.monotonic()
            try: test_one(selected_args,entry)
            finally: entry['elapsed_seconds'] = time.monotonic()-started
            entry['status'] = 'passed'; save(out/'pilot.json',manifest)
        manifest['status'] = 'finished'
    except BaseException:
        manifest['status'] = 'failed_or_interrupted'
        for entry in manifest['runs']:
            if entry['status']=='running': entry['status']='failed_or_interrupted'
            elif entry['status']=='pending': entry['status']='not_run_after_failure'
        raise
    finally:
        complete = collect_pilot(out,manifest)
    if not complete: raise RuntimeError('Pilot workload coverage is incomplete; inspect pilot.json and ReFrame reports.')

def main():
    if len(sys.argv)>1 and sys.argv[1]=='osu':
        sys.path.insert(0,str(HERE/'production'))
        from osu import main as osu_main
        return osu_main(sys.modules[__name__],sys.argv[2:])
    if len(sys.argv)>1 and sys.argv[1]=='production':
        sys.path.insert(0,str(HERE/'production'))
        from campaign import main as production_main
        return production_main(sys.modules[__name__],sys.argv[2:])
    if len(sys.argv)>1 and sys.argv[1]=='--effective-flags':
        for key,value in effective().items(): print('export '+key+'='+shlex.quote(value))
        return
    parser = argparse.ArgumentParser(description='Standalone GCC hardening setup, independent package builds and ReFrame pilots.')
    subs = parser.add_subparsers(dest='command',required=True)
    subs.add_parser('production',help='Audited dense MPI sustained-work comparisons; production --help for options.')
    subs.add_parser('osu',help='Pinned source preparation, offline fixed-caller build and paired MPI/UCX tests; osu --help for options.')
    subs.add_parser('setup'); subs.add_parser('refresh-tests'); subs.add_parser('status'); subs.add_parser('logs')
    mpi_prep = subs.add_parser('prepare-mpi',help='Stage verified MPI/UCX archives on a login node; builds use local archives only.')
    mpi_mode = mpi_prep.add_mutually_exclusive_group()
    mpi_mode.add_argument('--from-dir',metavar='DIR')
    mpi_mode.add_argument('--check',action='store_true')
    prep = subs.add_parser('prepare-tests',help='Prepare ReFrame before testing; use --check on compute nodes.')
    mode = prep.add_mutually_exclusive_group()
    mode.add_argument('--wheelhouse',metavar='DIR')
    mode.add_argument('--check',action='store_true')
    for cmd in ('build','test'):
        p = subs.add_parser(cmd); p.add_argument('package',choices=['fftw','hdf5','lapack','all']); p.add_argument('--mpi',action='store_true')
        if cmd=='build': p.add_argument('--retry',action='store_true')
        else:
            p.add_argument('--pairs',type=int,default=10); p.add_argument('--nodes',type=int,default=2)
            p.add_argument('--ranks-per-node',type=int,choices=(1,4),default=1)
            p.add_argument('--slurm-overlap',action='store_true')
    args = parser.parse_args()
    if sys.version_info<(3,10): raise RuntimeError('Python 3.10 or newer is required.')
    for directory in ('state','pending'): (HERE/directory).mkdir(exist_ok=True)
    with (HERE/'lock').open('w') as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise RuntimeError('Another trial command is active in this root.')
        if args.command=='setup': setup()
        elif args.command=='refresh-tests': refresh_tests()
        elif args.command=='prepare-tests': prepare_tests(args)
        elif args.command=='prepare-mpi': prepare_mpi(args)
        elif args.command=='build':
            require_setup()
            targets = selected(args.package,args.mpi)
            if any(p.endswith('-mpi') for p in targets) and not os.environ.get('SLURM_JOB_ID'):
                raise RuntimeError('MPI package correctness tests need a Slurm allocation. Run the build command there, or start with a serial package.')
            print('Build plan: '+', '.join(targets)+'; full then reference, prerequisites included.')
            for p in targets:
                for arm in ('full','reference'): build_one(p,arm,args.retry)
            print('Build complete. Next: trial test fftw (or hdf5/lapack); add --mpi for a parallel package.')
        elif args.command=='test':
            if args.pairs<2 or args.nodes<1: raise RuntimeError('Use at least two pairs and one node.')
            test(args)
        elif args.command=='status':
            q = read(HERE/'qualification.json'); print('Qualification: '+(q['identity'] if q else 'run trial setup'))
            for path in sorted((HERE/'state').glob('*.json')):
                verify_state(path.stem); print(path.stem+': complete; artifacts verified')
            for path in sorted((HERE/'pending').glob('*.json')): print(path.stem+': incomplete; inspect logs then use build --retry')
        else:
            for path in sorted((ROOT/'logs/runner').glob('*.log'))[-12:]: print(path)

if __name__=='__main__':
    try: main()
    except (RuntimeError,OSError,subprocess.SubprocessError) as error:
        print(f'ERROR: {error}',file=sys.stderr); sys.exit(1)
```
