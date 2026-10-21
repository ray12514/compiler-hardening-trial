"""Read-only verification of recorded builds, actual compile commands and ELF controls."""

import argparse
import datetime
import fcntl
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile

PACKAGES = ('fftw','hdf5','blas','lapack','ucx','openmpi','fftw-mpi','hdf5-mpi')


def sha(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            value.update(block)
    return value.hexdigest()


def controls(tokens):
    """Project ordered GCC arguments onto the experimental controls and baseline."""
    values = {}
    for token in tokens:
        if re.fullmatch(r'-O(?:[0-3sgz]|fast)',token): values['optimization'] = token
        elif token.startswith(('-march=','-mtune=')): values[token.split('=')[0]] = token
        elif token in ('-flto','-fno-lto') or token.startswith('-flto='): values['lto'] = token
        elif token.startswith(('-fstack-protector','-fno-stack-protector')): values['stack'] = token
        elif token in ('-fstack-clash-protection','-fno-stack-clash-protection'): values['clash'] = token
        elif token.startswith('-fcf-protection='): values['cf'] = token
        elif token.startswith('-ftrivial-auto-var-init='): values['init'] = token
        elif token.startswith(('-D_FORTIFY_SOURCE','-U_FORTIFY_SOURCE')): values['fortify'] = token
        elif token.startswith(('-D_GLIBCXX_ASSERTIONS','-U_GLIBCXX_ASSERTIONS')): values['assertions'] = token
    return values


def compile_commands(build, logs):
    """Read generated CMake commands or real verbose compile lines, never flags.txt alone."""
    database = next((p for p in (logs/'compile_commands.json',build/'compile_commands.json') if p.is_file()),None)
    if database:
        entries = json.loads(database.read_text())
        commands = [v.get('arguments') or shlex.split(v['command']) for v in entries]
        provenance = database
    else:
        provenance = logs/'build.log'
        if not provenance.is_file(): return [], None
        commands = []
        for line in provenance.read_text(errors='replace').splitlines():
            if ' -c ' not in line: continue
            try: commands.append(shlex.split(line))
            except ValueError: continue
    rows = []
    compiler = re.compile(r'(?:.*-)?(?:gcc|g\+\+|gfortran|cc|c\+\+|mpicc|mpicxx|mpifort|mpif90)(?:-\d[\d.]*)?$')
    for tokens in commands:
        if '-c' not in tokens or '-E' in tokens: continue
        sources = [t for t in tokens if not t.startswith('-') and Path(t).suffix.lower() in ('.c','.cc','.cpp','.cxx','.f','.f90','.f95','.f03','.f08')]
        drivers = [t for t in tokens if compiler.fullmatch(Path(t).name)]
        if not sources or not drivers or any('CompilerId' in t or 'CMakeScratch' in t for t in sources): continue
        source = sources[-1]
        language = 'FFLAGS' if Path(source).suffix.lower().startswith('.f') else 'CXXFLAGS' if Path(source).suffix.lower()!='.c' or Path(source).suffix=='.C' else 'CFLAGS'
        rows.append({'source':source,'compiler':drivers[-1],'language':language,'controls':controls(tokens)})
    return rows, provenance


def check_commands(rows, flags):
    failures = []
    for row in rows:
        expected = controls(shlex.split(flags[row['language']]))
        for key, value in expected.items():
            if row['controls'].get(key)!=value:
                failures.append({'source':row['source'],'control':key,'expected':value,'observed':row['controls'].get(key)})
        # An unexpected positive hardening control also invalidates a reference contrast.
        for key in ('stack','clash','cf','init','fortify','assertions'):
            if key not in expected and key in row['controls']:
                failures.append({'source':row['source'],'control':key,'expected':'absent','observed':row['controls'][key]})
    return failures


def check_compilers(rows, compilers, mpi_prefix=None):
    failures = []
    for row in rows:
        language = {'CFLAGS':'CC','CXXFLAGS':'CXX','FFLAGS':'FC'}[row['language']]
        expected = {Path(compilers[language]['path']).resolve()}
        if mpi_prefix:
            wrapper = {'CC':'mpicc','CXX':'mpicxx','FC':'mpifort'}[language]
            expected.add((mpi_prefix/'bin'/wrapper).resolve())
        observed = Path(row['compiler'])
        if not observed.is_absolute() or observed.resolve() not in expected:
            failures.append({'source':row['source'],'control':'compiler','expected':sorted(map(str,expected)),
                             'observed':row['compiler']})
    return failures


def elf(path, flags):
    value = subprocess.check_output(['readelf','-W','-h','-l','-d','-s',str(path)],text=True,timeout=30)
    executable = bool(re.search(r'\bINTERP\b',value)) or bool(re.search(r'Type:\s+EXEC\b',value))
    expected = shlex.split(flags['EXE_LDFLAGS' if executable else 'SHARED_LDFLAGS'])
    row = {'path':str(path),'executable':executable,'relro':'GNU_RELRO' in value,
           'now':bool(re.search(r'BIND_NOW|FLAGS[^\n]*\bNOW\b',value)),
           'nonexecuting_stack':bool(re.search(r'GNU_STACK[^\n]*\bRW\b',value)) and not bool(re.search(r'GNU_STACK[^\n]*\bRWE\b',value)),
           'stack_canary_symbol':'__stack_chk_fail' in value,
           'fortified_symbols':sorted(set(re.findall(r'\b(__\w+_chk)\b',value))),'failures':[]}
    for option, property in (('-Wl,-z,relro','relro'),('-Wl,-z,now','now')):
        if row[property] != (option in expected): row['failures'].append(property+' differs from effective linker flags')
    if '-Wl,-z,noexecstack' in expected and not row['nonexecuting_stack']:
        row['failures'].append('missing or executable GNU_STACK')
    if executable:
        row['pie'] = bool(re.search(r'Type:\s+DYN\b',value))
        if row['pie'] != ('-pie' in expected): row['failures'].append('executable PIE differs from effective flags')
    return row


def compiler_inventory(driver):
    probe = 'source "$TRIAL_ROOT/env.sh"\n'+shlex.quote(sys.executable)+' -c '+shlex.quote(
        'import json,os; print(json.dumps({"compilers":{k:os.environ[k] for k in ("CC","CXX","FC")},'
        '"runtime":{k:os.environ[k] for k in ("PATH","LD_LIBRARY_PATH") if k in os.environ}}))')
    detected = subprocess.check_output(['bash','-euc',probe],env=driver.environment(),text=True,timeout=30)
    selected = json.loads(detected.splitlines()[-1])
    runtime = driver.environment() | selected['runtime']
    evidence = {}
    for language, compiler in selected['compilers'].items():
        if not Path(compiler).is_absolute(): raise RuntimeError('Saved compiler must have an absolute private path: '+language)
        version = subprocess.check_output([compiler,'-dumpfullversion'],env=runtime,text=True,timeout=30).strip()
        evidence[language] = {'path':compiler,'version':version,'sha256':sha(Path(compiler))}
        if version!='12.5.0': raise RuntimeError('Unexpected private compiler version: '+language)
    return evidence


def audit(driver, result_dirs):
    parent = driver.ROOT/'results/build-audit'; parent.mkdir(parents=True,exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ-'),dir=parent))
    evidence = {'schema_version':1,'status':'running','builds':[],'historical_results':[],
                'limitations':['Compile logs are retained evidence, not a cryptographic attestation of historical compiler execution.',
                'Missing canary/fortified symbols alone do not mean flags were omitted. Coverage and optimization affect emission.',
                'This audit does not run correctness suites, MPI, RDMA or timings.']}
    errors, incomplete = [], []
    states = {}
    try:
        driver.require_setup(check_measurements=False)
        qualification = driver.read(driver.HERE/'qualification.json')
        flags = {arm:driver.get_flags(arm) for arm in ('full','reference')}
        if qualification['flags']!=flags: raise RuntimeError('Current effective flags differ from saved qualification')
        evidence['qualification'] = qualification
        # Query the private compiler selected by the saved environment, not PATH's cc.
        evidence['compilers'] = compiler_inventory(driver)
        for arm in flags:
            for package in PACKAGES:
                name = package+'-'+arm
                print(f'Audit: {name}; verifying installed hashes and compiler/linker evidence',flush=True)
                row = {'name':name,'status':'running','failures':[]}
                evidence['builds'].append(row)
                try:
                    state = driver.verify_state(name)
                    if state['effective_profile']!=qualification: raise RuntimeError('Installed build has a different qualification')
                    states[name] = state
                    row['identity'] = state['identity']; row['artifact_count'] = len(state['artifacts'])
                    build, _ = driver.paths(package,arm)
                    logs = driver.ROOT/'logs'/(package+'-'+('fixed' if arm=='full' else 'reference')) if package in ('ucx','openmpi') else driver.ROOT/'logs'/package/arm
                    commands, provenance = compile_commands(build,logs)
                    row['compile_commands'] = commands; row['command_count'] = len(commands)
                    if provenance: row['command_evidence'] = {'path':str(provenance),'sha256':sha(provenance)}
                    row['failures'] += check_commands(commands,flags[arm])
                    mpi = driver.paths('openmpi',arm)[1] if package.endswith('-mpi') else None
                    row['failures'] += check_compilers(commands,evidence['compilers'],mpi)
                    if not commands:
                        incomplete.append(name+': no actual compile-command evidence'); row['status'] = 'incomplete'
                    row['elf'] = []
                    for relative in state['artifacts']:
                        path = driver.ROOT/relative
                        with path.open('rb') as stream: magic = stream.read(4)
                        if magic!=b'\x7fELF': continue
                        observed = elf(path,flags[arm]); row['elf'].append(observed)
                        row['failures'] += [{'artifact':relative,'reason':message} for message in observed['failures']]
                    if not row['elf']:
                        incomplete.append(name+': no ELF evidence'); row['status'] = 'incomplete'
                    if row['failures']: row['status'] = 'failed'
                    elif row['status']=='running': row['status'] = 'passed'
                except (RuntimeError,OSError,ValueError,subprocess.SubprocessError) as error:
                    row['status'] = 'failed'; row['failures'].append(str(error))
                if row['status']=='failed': errors.append(name)
                driver.save(out/'audit.json',evidence)
        for name, state in states.items():
            for package, identity in state.get('dependencies',{}).items():
                dependency = package+'-'+state['arm']
                if states.get(dependency,{}).get('identity')!=identity: errors.append(name+': dependency identity mismatch: '+dependency)
        for directory in result_dirs:
            manifest = driver.read(directory/'manifest.json')
            history = {'directory':str(directory),'status':'unverified'}
            evidence['historical_results'].append(history)
            if not manifest or any(not {'fftw-mpi','hdf5-mpi','openmpi','ucx'}<=set(manifest.get('library_stacks',{}).get(arm,{})) for arm in ('full','reference')):
                incomplete.append(str(directory)+': no saved stack manifest'); continue
            history['scope'] = manifest.get('scope','stack')
            history['campaign_status'] = manifest.get('status')
            mismatches = []
            for arm, packages in manifest['library_stacks'].items():
                for package, saved in packages.items():
                    if states.get(package+'-'+arm)!=saved: mismatches.append(package+'-'+arm)
            history['status'] = 'matched' if not mismatches else 'different_builds'
            history['mismatches'] = mismatches
            if mismatches: errors.append('Historical result has different builds: '+str(directory))
        evidence['errors'] = errors; evidence['incomplete'] = incomplete
        evidence['status'] = 'failed' if errors else 'incomplete' if incomplete else 'passed'
        evidence['historical_verification'] = 'not_supplied' if not result_dirs else 'see historical_results'
    except BaseException as error:
        evidence['status'] = 'failed_or_interrupted'; evidence['error'] = str(error)
        raise
    finally:
        driver.save(out/'audit.json',evidence)
        qualification = evidence.get('qualification',{})
        profile = qualification.get('identity','unrecorded')
        if not re.fullmatch(r'(?:complete|compatible)-[0-9a-f]{12}',profile): profile = 'unrecorded'
        reduced = sorted(language+':'+control for language,groups in qualification.get('policy',{}).get('disabled',{}).items()
            if language in ('c','cxx','fortran','link') for control in groups
            if control in ('stack','clash','cf','init','fortify','assertions','relro','now','pie'))
        driver.save(out/'shareable-summary.json',{'schema_version':1,'status':evidence['status'],
            'qualified_profile':profile,'compatibility_reductions':reduced,
            'historical_results_supplied':len(result_dirs),
            'historical_matches':sum(v['status']=='matched' for v in evidence['historical_results']),
            'builds':[{'package':row['name'],'status':row['status'],
                'compile_commands':row.get('command_count',0),'elf_files':len(row.get('elf',[])),
                'elf_files_with_canary_symbol':sum(bool(v.get('stack_canary_symbol')) for v in row.get('elf',[])),
                'elf_files_with_fortified_symbols':sum(bool(v.get('fortified_symbols')) for v in row.get('elf',[])),
                'failures':len(row['failures'])} for row in evidence['builds']]})
        (out/'summary.txt').write_text('Build audit: '+evidence['status']+'\nQualified profile: '+profile+
            '\nCompatibility reductions: '+(', '.join(reduced) or 'none recorded')+'\n'+
            '\n'.join(row['name']+': '+row['status']+' ('+str(row.get('command_count',0))+' compile commands)' for row in evidence['builds'])+
            '\nHistorical records: '+str(len(result_dirs))+' supplied.\n'+
            'Private details, paths, exact flags and failures: audit.json\n')
        print(f'Build audit: {evidence["status"]}; private evidence: {out}',flush=True)
    if evidence['status']!='passed': raise RuntimeError('Build audit did not pass; inspect '+str(out/'audit.json'))
    return out


def main(driver, argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results',type=Path,action='append',default=[],help='Optional original production result directory; repeat to verify historical stack identities')
    parser.add_argument('--result-pointer',type=Path,help='Write the private audit-directory pointer for batch automation')
    args = parser.parse_args(argv)
    with (driver.HERE/'lock').open('a') as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise RuntimeError('A trial command is active; audit after it finishes') from None
        out = audit(driver,[p.expanduser().resolve() for p in args.results])
        if args.result_pointer: driver.save(args.result_pointer,{'audit':str(out)})
        return out
