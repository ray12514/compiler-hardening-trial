"""Pinned offline OSU builds and fixed-caller MPI/UCX comparisons after production."""

import argparse
import csv
import datetime
import fcntl
import hashlib
import html
import json
import math
import os
from pathlib import Path, PurePosixPath
import random
import re
import shutil
import statistics
import subprocess
import tarfile
import tempfile
import time
import urllib.request

import campaign as shared
from collect_mpi_diagnostics import selected_env
from placement import make_layout

VERSION = '7.5.2'
ARCHIVE = 'osu-micro-benchmarks-'+VERSION+'.tar.gz'
SHA256 = '618de3d0b1122f73a9229177d2da1e5cd62e431190580cb915f2605849cbbbdc'
URL = 'https://mvapich.cse.ohio-state.edu/download/mvapich/'+ARCHIVE
TARGETS = {
    'osu_latency':'c/mpi/pt2pt/standard', 'osu_bw':'c/mpi/pt2pt/standard',
    'osu_allreduce':'c/mpi/collective/blocking', 'osu_alltoall':'c/mpi/collective/blocking',
}
MESSAGES = {'osu_latency':[1,1024,65536],'osu_bw':[1024,65536,1048576],
            'osu_allreduce':[16,1024,65536],'osu_alltoall':[16,1024,4096]}
# In 7.5.2, merely supplying --disable-papi incorrectly selects PAPI=yes.
# Omit that option: the verified release's default is no PAPI dependency.
CONFIGURE = ['--disable-cuda','--disable-rocm','--disable-openacc','--disable-sycl']


def digest(path):
    with path.open('rb') as stream:
        value = hashlib.sha256()
        for block in iter(lambda:stream.read(1024*1024),b''):
            value.update(block)
    return value.hexdigest()


def tree_digest(path):
    value = hashlib.sha256()
    for item in sorted(path.rglob('*')):
        if item.is_symlink():
            raise RuntimeError('Unexpected link in extracted OSU source')
        if item.is_file():
            value.update(str(item.relative_to(path)).encode()+b'\0'+digest(item).encode()+b'\n')
    return value.hexdigest()


def source(root):
    path = root/'downloads'/ARCHIVE
    if not path.is_file() or digest(path)!=SHA256:
        raise RuntimeError('Missing or incorrect OSU archive; run trial osu prepare on the login node (or --from-dir DIR)')
    return path


def prepare(root, args):
    if args.check:
        return source(root)
    destination = root/'downloads'/ARCHIVE
    destination.parent.mkdir(parents=True,exist_ok=True)
    if destination.exists():
        return source(root)
    handle, name = tempfile.mkstemp(prefix=ARCHIVE+'.',suffix='.part',dir=destination.parent)
    os.close(handle); temporary = Path(name)
    try:
        if args.from_dir:
            shutil.copyfile(Path(args.from_dir).expanduser()/ARCHIVE,temporary)
        else:
            with urllib.request.urlopen(URL,timeout=60) as response, temporary.open('wb') as stream:
                shutil.copyfileobj(response,stream)
        if digest(temporary)!=SHA256:
            raise RuntimeError('OSU source checksum mismatch; unverified archive was not installed')
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return source(root)


def extract(archive, destination):
    if digest(archive)!=SHA256:
        raise RuntimeError('OSU archive changed before extraction')
    with tarfile.open(archive) as package:
        members = package.getmembers()
        for item in members:
            parts = PurePosixPath(item.name).parts
            if not parts or parts[0]!='osu-micro-benchmarks-'+VERSION or '..' in parts or not (item.isdir() or item.isfile()):
                raise RuntimeError('Unexpected OSU archive member')
        # Archive is hash-pinned; links, special files and traversal were rejected.
        package.extractall(destination,members=members)


def build(driver, args):
    archive = source(driver.ROOT)  # Never attempts a download.
    driver.require_setup(check_measurements=False)
    driver.verify_test_tree('openmpi','reference')
    env = shared.runtime(driver.ROOT,'reference',False)
    flags = driver.get_flags('reference')
    identity = {'source_sha256':SHA256,'version':VERSION,'configure':CONFIGURE,'targets':TARGETS,
                'flags':flags,'mpi':driver.verify_state('openmpi-reference'),
                'ucx':driver.verify_state('ucx-reference'),'mpi_prefix':env['MPI_PREFIX']}
    key = hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
    folder = driver.ROOT/'build/osu'/key[:20]
    prefix = driver.ROOT/'install/osu/fixed'/key[:20]
    record = driver.HERE/'osu-build.json'
    if record.is_file():
        previous = json.loads(record.read_text())
        if previous['identity']==key:
            return verify_build(driver)
    if folder.exists() and not args.retry:
        raise RuntimeError('An unfinished OSU build exists; inspect its logs and use trial osu build --retry')
    folder.mkdir(parents=True,exist_ok=True)
    extracted = folder/('osu-micro-benchmarks-'+VERSION)
    fingerprint = folder/'source-tree.json'
    if not extracted.exists():
        extract(archive,folder)
        shared.save(fingerprint,{'sha256':tree_digest(extracted)})
    if not fingerprint.is_file() or tree_digest(extracted)!=json.loads(fingerprint.read_text())['sha256']:
        raise RuntimeError('Extracted OSU source changed; do not label a modified tree as the pinned release')
    work = folder/'build'; work.mkdir(exist_ok=True)
    env.update(CC=str(Path(env['MPI_PREFIX'])/'bin/mpicc'),CXX=str(Path(env['MPI_PREFIX'])/'bin/mpicxx'),
               CFLAGS=flags['EXE_CFLAGS'],CXXFLAGS=flags['EXE_CXXFLAGS'],CPPFLAGS='',
               LDFLAGS=flags['EXE_LDFLAGS']+' -Wl,--enable-new-dtags -Wl,-rpath,'+str(Path(env['MPI_PREFIX'])/'lib'))
    deadline = time.monotonic()+args.build_minutes*60
    logs = folder/'logs'; logs.mkdir(exist_ok=True)
    # The release archive includes configure and generated Makefiles; no autotools download.
    configure = folder/('osu-micro-benchmarks-'+VERSION)/'configure'
    shared.run(['bash','-c','cd "$1"; shift; exec "$@"','osu-build',str(work),
                str(configure),'--prefix='+str(prefix),*CONFIGURE],env,logs/'configure',args.build_minutes*60,deadline)
    binaries = {}
    for directory in dict.fromkeys(TARGETS.values()):
        names = [name for name,path in TARGETS.items() if path==directory]
        shared.run(['make','-C',str(work/directory),'-j',str(args.jobs),'V=1',*names],
                   env,logs/Path(directory).name,args.build_minutes*60,deadline)
        for name in names:
            target = prefix/'bin'/name
            target.parent.mkdir(parents=True,exist_ok=True)
            temporary = target.with_suffix('.tmp')
            shutil.copy2(work/directory/name,temporary); temporary.replace(target)
            elf = subprocess.check_output(['readelf','-W','-h','-l','-d',str(target)],env=env,text=True,timeout=30)
            (logs/(name+'.elf.txt')).write_text(elf)
            binaries[name] = {'path':str(target),'sha256':digest(target)}
    value = {'identity':key,'scope':'fixed-reference-caller','version':VERSION,'build':identity,
             'binaries':binaries,'logs':str(logs),'config_log':str(work/'config.log'),
             'source_tree_sha256':tree_digest(extracted)}
    shared.save(record,value)
    return verify_build(driver)


def verify_build(driver):
    record = driver.HERE/'osu-build.json'
    if not record.is_file():
        raise RuntimeError('OSU is not built; run trial osu build using the staged archive')
    value = json.loads(record.read_text())
    if (value['version']!=VERSION or value['build']['source_sha256']!=SHA256 or set(value['binaries'])!=set(TARGETS)
        or value['build']['configure']!=CONFIGURE or value['build']['targets']!=TARGETS):
        raise RuntimeError('OSU build identity differs from the pinned adapter')
    for binary in value['binaries'].values():
        path = Path(binary['path'])
        if not path.is_file() or digest(path)!=binary['sha256']:
            raise RuntimeError('OSU executable changed or is missing; inspect the build before testing')
    for package in ('openmpi','ucx'):
        if driver.verify_state(package+'-reference')!=value['build']['mpi' if package=='openmpi' else 'ucx']:
            raise RuntimeError('Reference MPI/UCX changed since the OSU caller was built; rebuild OSU')
    if driver.get_flags('reference')!=value['build']['flags']:
        raise RuntimeError('Ordinary caller flags changed; rebuild OSU before comparing runtimes')
    return value


def parse_output(text, name, size, validation=False):
    unit = 'MB/s' if name=='osu_bw' else 'us'
    header = r'Bandwidth\s*\(MB/s\)' if unit=='MB/s' else r'Latency\s*\(us\)'
    if not re.search(r'OSU.*\bv'+re.escape(VERSION)+r'\b',text) or not re.search(header,text):
        raise RuntimeError('Unexpected OSU version or native metric header')
    datatype = 'MPI_INT' if name=='osu_allreduce' else 'MPI_CHAR'
    if re.findall(r'# Datatype:\s*(\w+)\.',text)!=[datatype]:
        raise RuntimeError('Unexpected OSU datatype')
    rows = [line.split() for line in text.splitlines() if re.match(r'^\s*\d+\s',line)]
    if len(rows)!=1 or int(rows[0][0])!=size:
        raise RuntimeError('Missing/duplicate/unexpected OSU message-size row')
    value = float(rows[0][1])
    if not math.isfinite(value) or value<=0:
        raise RuntimeError('Invalid OSU native metric')
    if validation and (rows[0][-1].lower()!='pass' or re.search(r'\bFAIL(?:ED)?\b|DATA VALIDATION ERROR',text,re.I)):
        raise RuntimeError('OSU data validation did not pass')
    return value, unit


def arguments(size, args, validation=False):
    return ['-m',f'{size}:{size}','-i',str(args.iterations),'-x',str(args.warmups)]+(['--validation'] if validation else [])


def memory_required(name, size, ranks):
    # Conservative buffers plus a fixed MPI/UCX/runtime reserve. The OSU bandwidth
    # window is pinned at the release default (64), not a rank-saturation claim.
    multiplier = 8*ranks if name=='osu_alltoall' else 8*64 if name=='osu_bw' else 8
    return 256*1024**2+size*multiplier


def prior_production(path, stacks):
    value = json.loads((path/'manifest.json').read_text())
    if value.get('status')!='finished' or value.get('scope')!='deployment':
        raise RuntimeError('Run and complete the next fixed-caller production test before OSU')
    for arm in ('full','reference'):
        for package in ('openmpi','ucx'):
            if value.get('library_stacks',{}).get(arm,{}).get(package)!=stacks[arm][package]:
                raise RuntimeError('Production and OSU MPI/UCX build identities differ')
    return {'path':str(path),'procedure_commit':value.get('procedure_commit'),
            'scope':value['scope'],'status':value['status']}


def report(out):
    manifest = json.loads((out/'manifest.json').read_text())
    rows, summaries = [], []
    for case in manifest['conditions']:
        complete = []
        for pair in case['pairs']:
            for arm,result in pair['results'].items():
                rows.append({'condition':case['name'],'pair':pair['pair'],'arm':arm,'bytes':case['bytes'],
                             'value':result['value'],'unit':case['unit'],
                             'process_elapsed_seconds':result['process_elapsed_seconds'],
                             'complete_pair':pair['status']=='passed'})
            if pair['status']=='passed':
                complete.append(pair)
        if not complete:
            continue
        full = [p['results']['full']['value'] for p in complete]
        reference = [p['results']['reference']['value'] for p in complete]
        change = 100*(statistics.mean(full)/statistics.mean(reference)-1)
        low,high = shared.interval(full,reference,manifest['seed'])
        if case['benchmark']=='osu_bw':
            change = -change
            low,high = (-high,-low) if low is not None else (None,None)
        summaries.append({'condition':case['name'],'benchmark':case['benchmark'],'bytes':case['bytes'],
            'scope':'fixed-caller-mpi-ucx','nodes':case['nodes'],'ranks_per_node':case['ranks_per_node'],
            'pairs':len(complete),'requested_pairs':manifest['requested_pairs'],'status':case['status'],
            'unit':case['unit'],'full_mean':statistics.mean(full),'reference_mean':statistics.mean(reference),
            'full_stdev':statistics.stdev(full) if len(full)>1 else None,
            'reference_stdev':statistics.stdev(reference) if len(reference)>1 else None,
            'deterioration_percent':change,'interval_low_percent':low,'interval_high_percent':high})
    for name,values,fields in (
        ('pairs.csv',rows,['condition','pair','arm','bytes','value','unit','process_elapsed_seconds','complete_pair']),
        ('summary.csv',summaries,['condition','benchmark','bytes','scope','nodes','ranks_per_node','pairs','requested_pairs','status',
                                'unit','full_mean','reference_mean','full_stdev','reference_stdev',
                                'deterioration_percent','interval_low_percent','interval_high_percent'])):
        with (out/name).open('w',newline='') as stream:
            writer = csv.DictWriter(stream,fieldnames=fields); writer.writeheader(); writer.writerows(values)
    shared.save(out/'summary.json',{'schema_version':1,'status':manifest['status'],'scope':'fixed-caller-mpi-ucx',
                'summaries':summaries,'uncertainty':'95% paired process bootstrap, ratio of arithmetic means; 2000 resamples'})
    columns = ['condition','status','pairs','requested_pairs','full_mean','reference_mean','unit',
               'deterioration_percent','interval_low_percent','interval_high_percent']
    table = ''.join('<tr>'+''.join('<td>'+html.escape(str(row[k]))+'</td>' for k in columns)+'</tr>' for row in summaries)
    extent = max([1]+[abs(r[k]) for r in summaries for k in ('deterioration_percent','interval_low_percent','interval_high_percent') if r[k] is not None])*1.1
    graph = []
    for i,row in enumerate(summaries):
        y = 22+32*i; x = lambda v: 700+v/extent*250
        color = '#b35932' if row['deterioration_percent']>0 else '#167d8d'
        graph.append(f'<text x="5" y="{y+4}">{html.escape(row["condition"])}</text><circle cx="{x(row["deterioration_percent"])}" cy="{y}" r="4" fill="{color}"/>')
        if row['interval_low_percent'] is not None:
            graph.append(f'<line x1="{x(row["interval_low_percent"])}" x2="{x(row["interval_high_percent"])}" y1="{y}" y2="{y}" stroke="{color}"/>')
    height = max(50,len(summaries)*32+30)
    (out/'report.html').write_text('<!doctype html><meta charset="utf-8"><title>OSU fixed-caller comparison</title>'
        '<style>body{font:15px system-ui;margin:2em}td,th{padding:.4em;text-align:left}svg{width:100%;max-width:1100px}</style>'
        '<h1>OSU: fixed caller, reference versus hardened MPI/UCX</h1><p>Campaign status: '+html.escape(manifest['status'])+
        '. Positive deterioration means higher latency or lower bandwidth. Native metrics retain their units. '
        'Whiskers show paired 95% intervals; points alone do not establish significance. Completion is not overhead acceptance.</p>'
        f'<svg viewBox="0 0 1000 {height}"><line x1="700" x2="700" y1="0" y2="{height}" stroke="#888"/>'+''.join(graph)+'</svg>'
        '<p>Horizontal scale: +/- '+f'{extent:.2f}'+'% deterioration; vertical line is zero. Unmeasured conditions remain in manifest.json.</p>'
        '<table><tr>'+''.join('<th>'+k+'</th>' for k in columns)+'</tr>'+table+'</table>')
    print(f'OSU analysis: {out}/report.html\nOSU CSV: {out}/summary.csv',flush=True)
    return summaries


def test(driver, args):
    driver.require_setup(check_measurements=False)
    build_info = verify_build(driver)
    stacks = {arm:{package:driver.verify_state(package+'-'+arm) for package in ('openmpi','ucx')}
              for arm in ('full','reference')}
    for arm in stacks:
        driver.verify_test_tree('openmpi',arm)
    prior = prior_production(args.after_production.expanduser().resolve(),stacks)
    hosts, counts, tasks, job = shared.allocation()
    selected = args.hosts.split(',') if args.hosts else hosts
    if len(set(selected))!=len(selected) or not set(selected)<=set(hosts) or len(selected)<max(args.nodes):
        raise RuntimeError('Selected OSU node scales/hosts do not fit this allocation')
    parent = driver.ROOT/'results/osu'; parent.mkdir(parents=True,exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ-'),dir=parent))
    started = time.monotonic(); deadline = started+args.budget_minutes*60
    remaining = subprocess.check_output(['squeue','-h','-j',os.environ['SLURM_JOB_ID'],'-o','%L'],text=True,timeout=15).strip()
    if re.fullmatch(r'(?:\d+-)?\d+:\d+(?::\d+)?',remaining):
        day,clock = remaining.split('-') if '-' in remaining else ('0',remaining)
        seconds = int(day)*86400+sum(v*60**i for i,v in enumerate(reversed(list(map(int,clock.split(':'))))))
        deadline = min(deadline,started+seconds-120)
    manifest = {'schema_version':1,'scope':'fixed-caller-mpi-ucx','status':'inventory','seed':args.seed,
        'requested_pairs':args.pairs,'arguments':{k:str(v) if isinstance(v,Path) else v for k,v in vars(args).items()},
        'prior_production':prior,'library_stacks':stacks,'osu_build':build_info,
        'procedure_commit':(driver.HERE/'procedure.txt').read_text().strip(),'hosts':selected,
        'job_id':os.environ['SLURM_JOB_ID'],'conditions':[]}
    (out/'slurm-job.txt').write_text(job)
    shared.save(out/'manifest.json',manifest)
    print(f'OSU evidence (private rank/library inventory): {out}',flush=True)
    try:
        infos = shared.audit(args,out,selected,deadline,counts)
        if len({json.dumps(i.get('hardware',{}),sort_keys=True) for i in infos.values()})!=1:
            raise RuntimeError('Use homogeneous CPU host groups for each OSU comparison')
        for name in args.benchmarks:
            placements = [(2,'1')] if name in ('osu_latency','osu_bw') else [(n,r) for n in args.nodes for r in args.ranks_per_node]
            for nodes,density in placements:
                layout = make_layout(infos,selected[:nodes],density,counts,tasks)
                layout['job_id'] = os.environ['SLURM_JOB_ID']
                for host,row in layout['hosts'].items():
                    memory = infos[host]['available_memory_bytes']
                    if os.environ.get('SLURM_MEM_PER_NODE','').isdigit() and int(os.environ['SLURM_MEM_PER_NODE'])>0:
                        memory = min(memory,int(os.environ['SLURM_MEM_PER_NODE'])*1024**2)
                    elif os.environ.get('SLURM_MEM_PER_CPU','').isdigit() and int(os.environ['SLURM_MEM_PER_CPU'])>0:
                        memory = min(memory,int(os.environ['SLURM_MEM_PER_CPU'])*1024**2*counts[host])
                    row['memory_budget_bytes'] = int(memory*args.memory_fraction)
                lane = f'{nodes}nodes-{layout["ranks_per_node"]}rpn'
                shared.save(out/(lane+'-layout.json'),layout)
                for size in args.messages or MESSAGES[name]:
                    label = lane+'-'+name+'-'+str(size)+'B'
                    if name=='osu_allreduce' and (size<4 or size%4):
                        raise RuntimeError('OSU allreduce byte counts must contain complete MPI_INT elements (multiples of four)')
                    if any(c['name']==label for c in manifest['conditions']):
                        continue
                    if any(memory_required(name,size,nodes*layout['ranks_per_node'])>
                           row['memory_budget_bytes']//layout['ranks_per_node'] for row in layout['hosts'].values()):
                        raise RuntimeError(f'OSU buffer/runtime reserve exceeds declared per-rank memory: {label}')
                    manifest['conditions'].append({'name':label,'benchmark':name,'bytes':size,'nodes':nodes,
                        'ranks_per_node':layout['ranks_per_node'],'layout':lane+'-layout.json',
                        'unit':'MB/s' if name=='osu_bw' else 'us','status':'pending','pairs':[]})
        envs = {arm:shared.runtime(driver.ROOT,arm,args.slurm_overlap) for arm in ('full','reference')}
        if selected_env(envs['full'])!=selected_env(envs['reference']):
            raise RuntimeError('Full/reference MPI/UCX runtime settings differ')
        manifest['runtime_settings'] = selected_env(envs['full'])
        manifest['status'] = 'running'; shared.save(out/'manifest.json',manifest)
        rng = random.Random(args.seed)
        for case in manifest['conditions']:
            if deadline-time.monotonic()<10:
                raise shared.BudgetExhausted('OSU campaign budget exhausted before next condition')
            case['status'] = 'qualifying'; shared.save(out/'manifest.json',manifest)
            folder = out/case['name']; binary = build_info['binaries'][case['benchmark']]['path']
            def execute(arm,label,validation=False):
                result,text = shared.launch_process(envs[arm],binary,out/case['layout'],
                    arguments(case['bytes'],args,validation),folder/label,args,deadline,
                    qualify=validation,payload='osu')
                value,unit = parse_output(text,case['benchmark'],case['bytes'],validation)
                answer = {'value':value,'unit':unit,'process_elapsed_seconds':result['process_elapsed_seconds']}
                shared.save(folder/label/'result.json',answer)
                return answer
            # Independent validation runs (including RC device inventory) precede all timed pairs.
            validations = {arm:execute(arm,arm+'-validation',True) for arm in envs}
            case['qualification'] = validations
            orders = [('full','reference'),('reference','full')]*(args.pairs//2); rng.shuffle(orders)
            case['planned_order'] = orders; case['status'] = 'measuring'
            estimate = 2*(max(v['process_elapsed_seconds'] for v in validations.values())+5)
            for index,order in enumerate(orders):
                if time.monotonic()+estimate>deadline:
                    raise shared.BudgetExhausted('OSU budget cannot fit another complete process pair')
                pair = {'pair':index,'order':order,'status':'running','results':{}}
                case['pairs'].append(pair); shared.save(out/'manifest.json',manifest)
                for arm in order:
                    print(f'{case["name"]}: pair {index+1}/{args.pairs}, {arm}',flush=True)
                    pair['results'][arm] = execute(arm,f'pair-{index:03d}-{arm}')
                    shared.save(out/'manifest.json',manifest)
                pair['status'] = 'passed'; shared.save(out/'manifest.json',manifest)
                estimate = max(estimate,sum(v['process_elapsed_seconds'] for v in pair['results'].values())+10)
            case['status'] = 'passed'; shared.save(out/'manifest.json',manifest); report(out)
        manifest['status'] = 'finished'
        return out
    except shared.BudgetExhausted as error:
        manifest['status'] = 'budget_exhausted_partial'
        for case in manifest['conditions']:
            if case['status'] in ('qualifying','measuring'):
                case['status'] = 'budget_exhausted_partial'
        print(str(error),flush=True)
        return out
    except BaseException:
        manifest['status'] = 'failed_or_interrupted'
        for case in manifest['conditions']:
            if case['status'] in ('qualifying','measuring'):
                case['status'] = 'failed_or_interrupted'
        raise
    finally:
        manifest['elapsed_seconds'] = time.monotonic()-started
        shared.save(out/'manifest.json',manifest); report(out)
        print(f'OSU campaign status: {manifest["status"]}',flush=True)


def main(driver, argv):
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command',required=True)
    prep = subs.add_parser('prepare',help='Login-node download/import; checks source hash, never builds')
    group = prep.add_mutually_exclusive_group(); group.add_argument('--from-dir',type=Path); group.add_argument('--check',action='store_true')
    builder = subs.add_parser('build',help='Offline build of four fixed ordinary callers; no MPI runs')
    builder.add_argument('--jobs',type=int,default=1); builder.add_argument('--build-minutes',type=float,default=30)
    builder.add_argument('--retry',action='store_true'); builder.add_argument('--check',action='store_true')
    tester = subs.add_parser('test',help='Paired MPI/UCX comparison after a completed production workflow')
    tester.add_argument('--after-production',type=Path,required=True)
    tester.add_argument('--benchmarks',default=','.join(TARGETS))
    tester.add_argument('--nodes',default='2'); tester.add_argument('--ranks-per-node',default='16')
    tester.add_argument('--hosts'); tester.add_argument('--messages',help='Optional explicit byte sizes for all selected benchmarks')
    tester.add_argument('--pairs',type=int,default=10); tester.add_argument('--iterations',type=int,default=1000)
    tester.add_argument('--warmups',type=int,default=100); tester.add_argument('--seed',type=int,default=17017)
    tester.add_argument('--timeout',type=int,default=300); tester.add_argument('--budget-minutes',type=float,default=90)
    tester.add_argument('--memory-fraction',type=float,default=.25); tester.add_argument('--slurm-overlap',action='store_true')
    group = tester.add_mutually_exclusive_group(); group.add_argument('--reserved-cpus'); group.add_argument('--reservations')
    tester.add_argument('--reframe',action='store_true'); tester.add_argument('--result-pointer',type=Path,help=argparse.SUPPRESS)
    reporter = subs.add_parser('report',help='Offline CSV/JSON/HTML regeneration; no measurements')
    reporter.add_argument('directory',type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command=='build' and (not 1<=args.jobs<=1024 or not math.isfinite(args.build_minutes) or not 1<=args.build_minutes<=1440):
            raise ValueError('Use 1..1024 build jobs and 1..1440 build minutes')
        if args.command=='test':
            args.benchmarks = list(dict.fromkeys(args.benchmarks.split(',')))
            args.nodes = list(dict.fromkeys(map(int,args.nodes.split(','))))
            args.ranks_per_node = list(dict.fromkeys(args.ranks_per_node.split(',')))
            args.messages = list(dict.fromkeys(map(int,args.messages.split(',')))) if args.messages else None
            if not args.benchmarks or not set(args.benchmarks)<=set(TARGETS) or min(args.nodes)<2:
                raise ValueError('Select supported OSU benchmarks and node scales >=2')
            if any(r!='all' and int(r)<1 for r in args.ranks_per_node) or args.messages and not all(1<=m<=1048576 for m in args.messages):
                raise ValueError('Use positive rank counts or all, and message sizes 1..1048576 bytes')
            if 'osu_allreduce' in args.benchmarks and args.messages and any(m<4 or m%4 for m in args.messages):
                raise ValueError('Allreduce byte sizes must contain complete MPI_INT elements (multiples of four)')
            if args.pairs<2 or args.pairs%2 or not 1<=args.iterations<=1000000 or not 1<=args.warmups<=100000:
                raise ValueError('Use even pairs >=2 and bounded positive OSU iterations/warmups')
            if not 5<=args.timeout<=3600 or not math.isfinite(args.budget_minutes) or args.budget_minutes<=0 or not 0<args.memory_fraction<=.75:
                raise ValueError('Invalid timeout, campaign budget or memory fraction')
    except ValueError as error:
        parser.error(str(error))
    if args.command=='report':
        return report(args.directory.expanduser().resolve())
    if args.command=='test' and args.reframe:
        return shared.run_reframe(driver,argv,args,command_name='osu')
    with (driver.HERE/'lock').open('a') as lock:
        try:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('A trial command is active; run OSU after it finishes') from None
        if args.command=='prepare':
            path = prepare(driver.ROOT,args); print(f'OSU source verified: {path}'); return path
        if args.command=='build':
            value = verify_build(driver) if args.check else build(driver,args)
            print(f'OSU fixed callers verified: {value["identity"]}; no MPI benchmarks were run'); return value
        out = test(driver,args)
        if args.result_pointer:
            shared.save(args.result_pointer,{'campaign':str(out)})
        return out
