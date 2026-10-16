"""Bounded production-density full/reference comparison using completed libraries."""

import argparse
import csv
import datetime
import fcntl
import hashlib
import html
import json
import math
import os
from pathlib import Path
import random
import re
import shlex
import shutil
import signal
import statistics
import subprocess
import sys
import tempfile
import time

from placement import eligible, make_layout
from collect_mpi_diagnostics import activated_env, selected_env

HERE = Path(__file__).resolve().parent
MODES = ('fft', 'collective', 'independent', 'integrated')


class BudgetExhausted(RuntimeError):
    pass


def save(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')
    temporary.replace(path)


def expand_counts(text):
    values = []
    for part in text.split(','):
        match = re.fullmatch(r'(\d+)(?:\(x(\d+)\))?', part)
        if not match:
            raise RuntimeError('Cannot parse SLURM_JOB_CPUS_PER_NODE; no allocation size assumed')
        values.extend([int(match[1])] * int(match[2] or 1))
    return values


def allocation():
    job = os.environ.get('SLURM_JOB_ID')
    if not job:
        raise RuntimeError('Run production tests inside the existing Slurm compute allocation')
    hosts = subprocess.check_output(['scontrol','show','hostnames',os.environ['SLURM_JOB_NODELIST']],
                                    text=True, timeout=15).split()
    hosts = [host.split('.')[0] for host in hosts]
    counts = expand_counts(os.environ.get('SLURM_JOB_CPUS_PER_NODE',''))
    if len(counts) != len(hosts) or len(set(hosts)) != len(hosts):
        raise RuntimeError('Job CPU counts do not match the allocated hosts')
    details = subprocess.check_output(['scontrol','show','job','-o',job], text=True, timeout=15)
    tasks = re.search(r'\bNumTasks=(\d+)\b', details)
    per_node = re.search(r'\bNtasksPerN:B:S:C=(\d+):', details)
    if not tasks or int(tasks[1]) < 1:
        raise RuntimeError('Cannot verify the job task/slot limit from scontrol')
    if per_node and int(per_node[1]):
        counts = [min(count,int(per_node[1])) for count in counts]
    return hosts, dict(zip(hosts,counts)), int(tasks[1]), details


def run(command, env, folder, timeout, deadline):
    folder.mkdir(parents=True, exist_ok=True)
    log = folder/'command.log'
    remaining = deadline-time.monotonic()
    if remaining < 5:
        raise RuntimeError('Run budget exhausted before launch')
    seconds = max(1, min(timeout, int(remaining)))
    started = time.monotonic()
    result = {'command': command, 'timeout_seconds': seconds, 'status': 'running'}
    save(folder/'command.json',result)
    with log.open('w') as stream:
        proc = subprocess.Popen(command, env=env, stdout=stream, stderr=subprocess.STDOUT,
                                start_new_session=True)
        try:
            while True:
                left = seconds-(time.monotonic()-started)
                if left <= 0:
                    raise subprocess.TimeoutExpired(command,seconds)
                try:
                    proc.wait(timeout=min(30,left))
                    break
                except subprocess.TimeoutExpired:
                    if time.monotonic()-started < seconds:
                        print(f'  still running: {folder.name}; log {log}',flush=True)
                    else:
                        raise
        except BaseException:
            try:
                os.killpg(proc.pid,signal.SIGTERM)
                proc.wait(timeout=3)
            except (ProcessLookupError,subprocess.TimeoutExpired):
                pass
            try:
                os.killpg(proc.pid,signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait()
            result.update(status='failed_or_interrupted', returncode=proc.returncode,
                          process_elapsed_seconds=time.monotonic()-started)
            save(folder/'command.json',result)
            raise
    result.update(status='passed' if proc.returncode==0 else 'failed', returncode=proc.returncode,
                  process_elapsed_seconds=time.monotonic()-started)
    save(folder/'command.json',result)
    if proc.returncode:
        raise RuntimeError(f'Command failed (exit {proc.returncode}); inspect {log}')
    return result, log.read_text(errors='replace')


def runtime(root, arm, overlap):
    env, note = activated_env(root,arm)
    if env is None:
        raise RuntimeError(note)
    transports = set(env.get('UCX_TLS','').split(','))
    if not transports & {'rc','rc_mlx5','rc_verbs'} or not transports <= {'rc','rc_mlx5','rc_verbs','sm','self'}:
        raise RuntimeError('Saved UCX_TLS must select RC with optional sm,self; no TCP fallback is accepted')
    env.update(TRIAL_ROOT=str(root), TRIAL_MPI_PREFIX=env['MPI_PREFIX'],
               TRIAL_UCX_PREFIX=env.pop('UCX_PREFIX'), TRIAL_PRODUCTION_ARM=arm,
               OMPI_MCA_pml='ucx')
    env.pop('UCX_LOG_LEVEL',None)
    if overlap:
        args = shlex.split(env.get('OMPI_MCA_plm_slurm_args',''))
        if '--overlap' not in args:
            args.append('--overlap')
        env['OMPI_MCA_plm_slurm_args'] = shlex.join(args)
    for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','BLIS_NUM_THREADS',
                'VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS'):
        env[key] = '1'
    return env


def audit(args, out, hosts, deadline, cpu_counts):
    folder = out/'inventory'
    folder.mkdir()
    allocation_counts = cpu_counts
    if os.environ.get('SLURM_JOB_CPUS_PER_NODE'):
        raw = expand_counts(os.environ['SLURM_JOB_CPUS_PER_NODE'])
        if len(raw)!=len(cpu_counts):
            raise RuntimeError('Allocation CPU counts changed before inventory')
        # Inventory the actual CPU grant before applying the rank-slot cap.
        allocation_counts = dict(zip(cpu_counts,raw))
    try:
        config = subprocess.check_output(['scontrol','show','config'],text=True,timeout=15)
        match = re.search(r'^\s*TaskPlugin\s*=\s*(\S+)',config,re.M)
        plugin = match[1] if match else ''
    except (OSError,subprocess.SubprocessError):
        plugin = ''
    # A whole-capacity task supplies actual OS CPU IDs even on task/affinity-only
    # sites. This is not an inference from the interactive shell's binding.
    for index,host in enumerate(hosts):
        count = allocation_counts[host]
        command = ['srun','--mpi=none','--nodes=1','--ntasks=1','--ntasks-per-node=1',
                   '--cpus-per-task='+str(count),'--cpu-bind=verbose,threads','--exact',
                   '--nodelist='+host,'--export=ALL']
        if args.slurm_overlap:
            command.append('--overlap')
        command += [sys.executable,str(HERE/'placement.py'),'--out',str(folder)]
        if args.reserved_cpus is not None:
            command += ['--reserved-cpus',args.reserved_cpus]
        if args.reservations:
            command += ['--reservations',str(Path(args.reservations).expanduser().resolve())]
        child = os.environ.copy()
        for key in ('SLURM_CPU_BIND','SLURM_CPU_BIND_LIST','SLURM_CPU_BIND_TYPE',
                    'SLURM_CPU_BIND_VERBOSE','SLURM_CPUS_PER_TASK','SLURM_TRES_PER_TASK'):
            child.pop(key,None)
        child.update(TRIAL_PRODUCTION_ALLOCATION_CPUS=str(count),TRIAL_PRODUCTION_TASK_PLUGIN=plugin)
        run(command,child,out/'audit'/f'node-{index}',args.timeout,deadline)
    infos = {}
    for host in hosts:
        path = folder/f'{host}.json'
        if not path.is_file():
            log = out/'audit'/f'node-{hosts.index(host)}'/'command.log'
            raise RuntimeError(f'Missing per-host CPU inventory; inspect {log}')
        info = json.loads(path.read_text())
        if info['job_id'] != os.environ['SLURM_JOB_ID'] or info['host'] != host:
            raise RuntimeError('Inventory host/job identity mismatch')
        infos[host] = info
    return infos


def shape_for(total_ranks, mib):
    # Both slab distributions are balanced; round up the target volume/rank.
    ny, nz = max(2,total_ranks), 64
    planes = max(1, math.ceil(mib*1024*1024/(16*ny*nz)))
    return [total_ranks*planes,ny,nz]


def host_groups(hosts, nodes, requested):
    groups = []
    for offset in range(0,len(hosts),nodes):
        group = [hosts[(offset+i)%len(hosts)] for i in range(nodes)]
        if set(group) not in [set(value) for value in groups]:
            groups.append(group)
        if len(groups)>=requested:
            break
    return groups


def compile_callers(driver, envs, out, args, deadline):
    source = (HERE/'workload.c').read_bytes()
    identities = {}
    for arm, env in envs.items():
        flags = driver.get_flags(arm)
        state = {p: driver.verify_state(p+'-'+arm) for p in ('fftw-mpi','hdf5-mpi','openmpi','ucx')}
        identity = hashlib.sha256(source+json.dumps([flags,state],sort_keys=True).encode()).hexdigest()
        folder = driver.ROOT/'runner/production-build'/identity/arm
        folder.mkdir(parents=True,exist_ok=True)
        binary = folder/'loop'
        if not binary.exists():
            (folder/'workload.c').write_bytes(source)
            command = [str(Path(env['MPI_PREFIX'])/'bin/mpicc'),*shlex.split(flags['EXE_CFLAGS']),
                       '-Wall','-Wextra','-Werror',str(folder/'workload.c')]
            for package in ('fftw-mpi','hdf5-mpi'):
                prefix = driver.ROOT/'install'/package/arm
                command += ['-I'+str(prefix/'include'),'-L'+str(prefix/'lib'),
                            '-Wl,--enable-new-dtags','-Wl,-rpath,'+str(prefix/'lib')]
            command += ['-lfftw3_mpi','-lfftw3','-lhdf5','-lm',*shlex.split(flags['EXE_LDFLAGS']),'-o',str(folder/'loop.tmp')]
            run(command,env,out/('compile-'+arm),max(args.timeout,300),deadline)
            (folder/'loop.tmp').replace(binary)
            save(folder/'identity.json',{'source_sha256':hashlib.sha256(source).hexdigest(),
                 'flags':flags,'state':state,'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest()})
        saved = json.loads((folder/'identity.json').read_text())
        if hashlib.sha256(binary.read_bytes()).hexdigest() != saved['binary_sha256']:
            raise RuntimeError('Production caller changed after compilation')
        identities[arm] = {'binary':str(binary),'identity':identity,**saved}
    return identities


def launch(env, binary, layout_path, arguments, folder, args, deadline, qualify=False):
    layout = json.loads(layout_path.read_text())
    rpn = layout['ranks_per_node']
    hosts = list(layout['hosts'])
    child = env.copy()
    child['TRIAL_PRODUCTION_QUALIFY'] = '1' if qualify else '0'
    if qualify:
        child['UCX_LOG_LEVEL'] = 'info'
    command = [str(Path(env['MPI_PREFIX'])/'bin/mpirun'),'-np',str(len(hosts)*rpn),
               '--host',','.join(f'{host}:{rpn}' for host in hosts),'--nooversubscribe',
               '--map-by',f'ppr:{rpn}:node','--bind-to','none',
               '--timeout',str(min(args.timeout,max(1,int(deadline-time.monotonic())-1))),
               '--mca','pml','ucx']
    for name in ('btl','mtl','plm_slurm_args'):
        if child.get('OMPI_MCA_'+name):
            command += ['--mca',name,child['OMPI_MCA_'+name]]
    command += [sys.executable,str(HERE/'rank.py'),str(layout_path),str(folder),binary,*map(str,arguments)]
    result, text = run(command,child,folder,args.timeout,deadline)
    matches = re.findall(r'^PRODUCTION_RESULT (.+)$',text,re.M)
    if len(matches) != 1:
        raise RuntimeError(f'Missing/duplicate workload result; inspect {folder}/command.log')
    value = json.loads(matches[0])
    if qualify and value.get('qualification_passed') is not True:
        raise RuntimeError('Communication qualification did not pass')
    if 'loop_seconds' in value and (not math.isfinite(value['loop_seconds']) or value['loop_seconds']<=0):
        raise RuntimeError('Workload returned an invalid loop duration')
    for rank in range(len(hosts)*rpn):
        info = json.loads((folder/f'rank-{rank}.json').read_text())
        row = layout['hosts'][info['host']]
        if info['rank']!=rank or info['cpus'] != [row['cpus'][info['local_rank']]]:
            raise RuntimeError('Observed rank affinity differs from the qualified map')
    observed = [json.loads(path.read_text()) for path in folder.glob('rank-*.json')]
    if len(observed)!=len(hosts)*rpn or len({(v['host'],v['local_rank']) for v in observed})!=len(observed):
        raise RuntimeError('Missing/duplicate local rank placement evidence')
    value['process_elapsed_seconds'] = result['process_elapsed_seconds']
    save(folder/'result.json',value)
    return value


def caller_args(mode, shape, steps, args, path, preflight=False):
    cadence = min(steps,args.checkpoint_every) if mode=='integrated' else 1
    return [mode,*shape,steps,cadence,int(args.io_mib_per_rank*1024*1024)//8,path,int(preflight)]


def interval(full, reference, seed):
    def effect(indices):
        return 100*(sum(full[i] for i in indices)/sum(reference[i] for i in indices)-1)
    count = len(full)
    if count<2:
        return None,None
    rng = random.Random(seed)
    samples = sorted(effect([rng.randrange(count) for _ in range(count)]) for _ in range(2000))
    return samples[49],samples[1949]


def report(out):
    manifest = json.loads((out/'manifest.json').read_text())
    rows, summaries, details = [], [], []
    for condition in manifest.get('conditions',[]):
        records = condition.get('pairs',[])
        full, reference = [], []
        for record in records:
            for arm, value in record.get('results',{}).items():
                row = {'condition':condition['name'],'pair':record['pair'],'arm':arm,
                       'nodes':condition['nodes'],'ranks_per_node':condition['ranks_per_node'],
                       'steps':condition.get('steps'),'loop_seconds':value['loop_seconds'],
                       'process_elapsed_seconds':value['process_elapsed_seconds'],
                       'planning_seconds':value['planning_seconds'],'checkpoints':value['checkpoints'],
                       'checkpoint_bytes':value['checkpoint_bytes'],'max_rank_rss_bytes':value['max_rank_rss_bytes'],
                       'error':value['error'],'complete_pair':record.get('status')=='passed'}
                rows.append(row)
                details.append(({k:row[k] for k in ('condition','pair','arm')},value))
            if record.get('status')=='passed':
                full.append(record['results']['full']['loop_seconds'])
                reference.append(record['results']['reference']['loop_seconds'])
        if full:
            lo,hi = interval(full,reference,manifest['seed'])
            summaries.append({'condition':condition['name'],'pairs':len(full),
                'requested_pairs':manifest['requested_pairs'],'status':condition['status'],
                'full_mean_seconds':statistics.mean(full),'reference_mean_seconds':statistics.mean(reference),
                'full_stdev_seconds':statistics.stdev(full) if len(full)>1 else None,
                'reference_stdev_seconds':statistics.stdev(reference) if len(reference)>1 else None,
                'delta_seconds':statistics.mean([f-r for f,r in zip(full,reference)]),
                'runtime_increase_percent':100*(statistics.mean(full)/statistics.mean(reference)-1),
                'interval_low_percent':lo,'interval_high_percent':hi})
    fields = {
        'pairs.csv': ['condition','pair','arm','nodes','ranks_per_node','steps','loop_seconds',
            'process_elapsed_seconds','planning_seconds','checkpoints','checkpoint_bytes','max_rank_rss_bytes','error','complete_pair'],
        'iterations.csv': ['condition','pair','arm','step','compute_maxrank_seconds','write_maxrank_seconds'],
        'io-modes.csv': ['condition','pair','arm','rank','step','actual_mode','local_cause','global_cause'],
        'summary.csv': ['condition','pairs','requested_pairs','status','full_mean_seconds','reference_mean_seconds',
            'full_stdev_seconds','reference_stdev_seconds','delta_seconds','runtime_increase_percent','interval_low_percent','interval_high_percent'],
    }
    for name, data in (('pairs.csv',rows),('iterations.csv',None),('io-modes.csv',None),('summary.csv',summaries)):
        with (out/name).open('w',newline='') as stream:
            writer = csv.DictWriter(stream,fieldnames=fields[name]); writer.writeheader()
            if data is not None:
                writer.writerows(data)
            else:
                for prefix,value in details:
                    raw = value
                    if value.get('result_file'):
                        path = (out/value['result_file']).resolve()
                        if not path.is_relative_to(out.resolve()):
                            raise RuntimeError('Result path is outside this campaign')
                        raw = json.loads(path.read_text())
                    key = 'iterations' if name=='iterations.csv' else 'io_modes'
                    writer.writerows({**prefix,**entry} for entry in raw.get(key,[]))
    save(out/'summary.json',{'schema_version':1,'status':manifest['status'],'summaries':summaries,
         'scope':'Complete matched stack; measured mini-application loops, not application-wide/security conclusions.',
         'uncertainty':'95% percentile bootstrap of fresh process pairs; iterations/ranks are not independent samples.'})
    # Standalone quick-look dashboard, no network or Python plotting dependency.
    # Data in this HTML contains only condition labels and aggregate measurements.
    table = ''.join('<tr>'+''.join('<td>'+html.escape(str(row[key]))+'</td>' for key in
        ('condition','pairs','delta_seconds','runtime_increase_percent','interval_low_percent','interval_high_percent'))+'</tr>'
        for row in summaries)
    payload = json.dumps(summaries).replace('<','\\u003c')
    (out/'report.html').write_text('''<!doctype html><meta charset="utf-8"><title>Production comparison</title>
<style>body{font:16px system-ui;max-width:1100px;margin:2em auto;padding:1em}td,th{padding:.5em;text-align:left}table{border-collapse:collapse}tr{border-bottom:1px solid #ddd}canvas{width:100%}</style>
<h1>Complete-stack runtime comparison</h1><p>Positive change means full is slower. Bars show paired mean runtime change; lines show 95% bootstrap intervals. Partial results are retained. Passing correctness does not establish acceptable overhead.</p>
<canvas id="chart"></canvas><table><tr><th>Condition</th><th>Pairs</th><th>Delta seconds</th><th>Change %</th><th>Low %</th><th>High %</th></tr>'''+table+'''</table>
<p>Use pairs.csv, iterations.csv and io-modes.csv for further analysis. Loop walltime is measured directly; do not sum per-phase maxima or multiply a percentage by the iteration count.</p>
<script>
const rows='''+payload+''';const c=document.getElementById('chart');c.width=1050;c.height=Math.max(100,rows.length*40+40);const x=c.getContext('2d');x.font='13px system-ui';
const extent=Math.max(1,...rows.flatMap(r=>[Math.abs(r.runtime_increase_percent),Math.abs(r.interval_low_percent||0),Math.abs(r.interval_high_percent||0)]))*1.1;
const pos=v=>650+v/extent*320;x.strokeStyle='#aaa';x.beginPath();x.moveTo(650,0);x.lineTo(650,c.height);x.stroke();
rows.forEach((r,i)=>{let y=i*40+24;x.fillStyle='#222';x.fillText(r.condition,4,y+4);x.fillStyle=r.runtime_increase_percent>0?'#b35932':'#267483';let p=pos(r.runtime_increase_percent);x.fillRect(Math.min(650,p),y-7,Math.max(1,Math.abs(p-650)),14);if(r.interval_low_percent!==null){x.strokeStyle='#111';x.beginPath();x.moveTo(pos(r.interval_low_percent),y);x.lineTo(pos(r.interval_high_percent),y);x.stroke();}x.fillStyle='#222';x.fillText(r.runtime_increase_percent.toFixed(2)+'%',975,y+4);});
</script>''')
    print(f'Analysis: {out}/report.html\nCSV: {out}/summary.csv',flush=True)
    return summaries


def campaign(driver, args):
    driver.require_setup(check_measurements=False)
    hosts, cpu_counts, tasks, details = allocation()
    if args.hosts:
        selected = args.hosts.split(',')
        if len(set(selected))!=len(selected) or not set(selected)<=set(hosts):
            raise RuntimeError('--hosts must name distinct hosts in this allocation')
    else:
        selected = hosts
    if max(args.nodes)>len(selected):
        raise RuntimeError('Requested node scale exceeds the selected allocation hosts')
    parent = driver.ROOT/'results/production'; parent.mkdir(parents=True,exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ-'),dir=parent))
    started = time.monotonic(); deadline = started+args.budget_minutes*60
    # Keep a cleanup margin before the scheduler's remaining job time.
    remaining = subprocess.check_output(['squeue','-h','-j',os.environ['SLURM_JOB_ID'],'-o','%L'],text=True,timeout=15).strip()
    if re.fullmatch(r'(?:\d+-)?\d+:\d+(?::\d+)?',remaining):
        day, clock = remaining.split('-') if '-' in remaining else ('0',remaining)
        fields = list(map(int,clock.split(':')))
        seconds = int(day)*86400 + sum(v*60**i for i,v in enumerate(reversed(fields)))
        deadline = min(deadline,started+seconds-120)
    manifest = {'schema_version':1,'status':'inventory','requested_pairs':args.pairs,'seed':args.seed,
                'job_id':os.environ['SLURM_JOB_ID'],'hosts':selected,'arguments':vars(args),
                'procedure_commit':(driver.HERE/'procedure.txt').read_text().strip(),
                'effective_profile':driver.read(driver.HERE/'qualification.json'),
                'scope':'stack','conditions':[],'logical_write_bytes_reserved':0,
                'budget_seconds':max(0,deadline-started),'scaling':'explicit fixed global FFT shape' if args.shape else 'volume per rank; rounded balanced slab shape',
                'completion':'HDF5 global flush and close; final restart read is outside loop timing; no physical-durability or cold-cache claim'}
    manifest['workflow_sha256'] = {p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in sorted(HERE.iterdir()) if p.suffix in ('.py','.c')}
    (out/'slurm-job.txt').write_text(details)
    save(out/'manifest.json',manifest)
    print(f'Production results (private inventory stays local): {out}',flush=True)
    try:
        infos = audit(args,out,selected,deadline,cpu_counts)
        safe_inventory = []
        for index,host in enumerate(selected):
            info = infos[host]
            candidates,_ = eligible(info)
            safe_inventory.append({'node_alias':f'node-{index}',
                'physical_cores':len({(v['socket'],v['core']) for v in info['topology'].values()}),
                'allocation_source':info.get('allocation_source','slurm-job-cgroup'),
                'job_allowed_os_cpus':len(info['allowed']),'eligible_physical_cores':len(candidates),
                'allocation_cpu_slot_cap':cpu_counts[host]})
        save(out/'shareable-inventory.json',safe_inventory)
        layouts = []
        signatures = {json.dumps(info.get('hardware',{}),sort_keys=True) for info in infos.values()}
        if len(signatures)!=1:
            raise RuntimeError('Selected hosts have different CPU hardware; compare homogeneous groups separately')
        requested_layouts = [(nodes,group_index,group,density) for nodes in args.nodes
                             for group_index,group in enumerate(host_groups(selected,nodes,args.groups_per_scale))
                             for density in args.ranks_per_node]
        for nodes,group_index,group,density in requested_layouts:
            layout = make_layout(infos,group,density,cpu_counts,tasks)
            layout['job_id'] = os.environ['SLURM_JOB_ID']
            rpn = layout['ranks_per_node']
            name = f'{nodes}nodes-'+(f'g{group_index}-' if group_index else '')+f'{rpn}rpn'
            if any(entry[0]==name for entry in layouts):
                continue
            for host,row in layout['hosts'].items():
                memory = infos[host]['available_memory_bytes']
                if os.environ.get('SLURM_MEM_PER_NODE','').isdigit() and int(os.environ['SLURM_MEM_PER_NODE'])>0:
                    memory = min(memory,int(os.environ['SLURM_MEM_PER_NODE'])*1024**2)
                elif os.environ.get('SLURM_MEM_PER_CPU','').isdigit() and int(os.environ['SLURM_MEM_PER_CPU'])>0:
                    memory = min(memory,int(os.environ['SLURM_MEM_PER_CPU'])*1024**2*cpu_counts[host])
                row['memory_budget_bytes'] = int(memory*args.memory_fraction)
            path = out/(name+'-layout.json'); save(path,layout)
            shape = args.shape or shape_for(nodes*rpn,args.fft_mib_per_rank)
            layouts.append((name,path,shape))
            capacities = [row['capacity'] for row in layout['hosts'].values()]
            print(f'{name}: {rpn} verified physical cores/node selected; safe capacities {capacities}; FFT shape {shape}',flush=True)
            for mode in args.workloads:
                manifest['conditions'].append({'name':name+'-'+mode,'layout':path.name,'nodes':nodes,
                    'ranks_per_node':rpn,'host_group':group_index,'shape':shape,'mode':mode,'status':'pending','pairs':[]})
        if args.audit_only:
            manifest['status'] = 'audit_passed_no_measurements'
            return out
        io = Path(os.environ.get('IO_DIR','')).expanduser()
        if not os.environ.get('IO_DIR') or not io.is_absolute():
            raise RuntimeError('Set IO_DIR to an absolute shared trial directory on the filesystem to measure')
        io.mkdir(parents=True,exist_ok=True)
        io = Path(tempfile.mkdtemp(prefix=out.name+'-',dir=io))
        manifest['io_directory'] = str(io)
        for package in ('fftw-mpi','hdf5-mpi'):
            for arm in ('full','reference'):
                driver.verify_test_tree(package,arm)
        envs = {arm:runtime(driver.ROOT,arm,args.slurm_overlap) for arm in ('full','reference')}
        if selected_env(envs['full']) != selected_env(envs['reference']):
            raise RuntimeError('Full/reference runtime settings differ; resolve before comparisons')
        manifest['runtime_settings'] = selected_env(envs['full'])
        identities = compile_callers(driver,envs,out,args,deadline)
        manifest['callers'] = identities
        manifest['status'] = 'running'; save(out/'manifest.json',manifest)
        rng = random.Random(args.seed)
        qualified = set()
        for condition in manifest['conditions']:
            if time.monotonic()+2*args.target_seconds+30 > deadline:
                manifest['status'] = 'budget_exhausted_partial'; break
            name,mode = condition['name'],condition['mode']
            folder = out/name; folder.mkdir()
            layout_path = out/condition['layout']
            layout = json.loads(layout_path.read_text())
            shape = condition['shape']
            if condition['layout'] not in qualified:
                for arm in ('full','reference'):
                    launch(envs[arm],identities[arm]['binary'],layout_path,['qualify'],
                           out/(condition['layout']+'-'+arm+'-qualification'),args,deadline,qualify=True)
                qualified.add(condition['layout'])
            condition['status'] = 'calibrating'; save(out/'manifest.json',manifest)
            # The exact same geometry and one-step work is queried in both arms.
            preflights = {}
            for arm in ('full','reference'):
                preflights[arm] = launch(envs[arm],identities[arm]['binary'],layout_path,
                    caller_args(mode,shape,1,args,io/(name+'-'+arm+'.h5'),True),folder/(arm+'-preflight'),args,deadline)
            keys = ('estimated_rank_bytes','local_slabs_min','local_slabs_max','checkpoint_bytes')
            if any(preflights['full'][k]!=preflights['reference'][k] for k in keys):
                raise RuntimeError('Full/reference caller geometry differs')
            size = preflights['full']['checkpoint_bytes']
            if size>args.max_checkpoint_gib*1024**3 or size*2>shutil.disk_usage(io).free:
                raise RuntimeError('Checkpoint exceeds the declared retained-file/free-space budget')
            condition['preflight'] = preflights
            def execute(arm,steps,label):
                count = math.ceil(steps/min(steps,args.checkpoint_every)) if mode=='integrated' else steps
                volume = size*count
                if manifest['logical_write_bytes_reserved']+volume>args.max_written_gib*1024**3:
                    raise BudgetExhausted('Campaign logical-write budget exhausted; partial results retained')
                manifest['logical_write_bytes_reserved'] += volume
                save(out/'manifest.json',manifest)
                result = launch(envs[arm],identities[arm]['binary'],layout_path,
                    caller_args(mode,shape,steps,args,io/(name+'-'+arm+'.h5')),folder/label,args,deadline)
                memory = min(row['memory_budget_bytes']//layout['ranks_per_node'] for row in layout['hosts'].values())
                if result['max_rank_rss_bytes']>memory:
                    raise RuntimeError('Measured peak RSS exceeds the declared per-rank memory budget')
                result_file = folder/label/'result.json'
                result_file.parent.mkdir(parents=True,exist_ok=True)
                save(result_file,result)
                return {**{key:value for key,value in result.items() if key not in ('iterations','io_modes')},
                        'result_file':str(result_file.relative_to(out))}
            # Calibration/warmup runs never enter the paired summary.
            initial_steps = args.checkpoint_every if mode=='integrated' else 1
            calibrations = {arm:execute(arm,initial_steps,arm+'-calibration') for arm in ('full','reference')}
            seconds = max(value['loop_seconds'] for value in calibrations.values())
            steps = max(initial_steps,min(args.max_steps,math.ceil(initial_steps*args.target_seconds/max(seconds,1e-6))))
            if mode=='integrated':
                steps = min(args.max_steps,(math.ceil(steps/args.checkpoint_every))*args.checkpoint_every)
            if size:
                remaining_io = sum(c['mode']!='fft' and c['status']!='passed' for c in manifest['conditions'])
                available = args.max_written_gib*1024**3-manifest['logical_write_bytes_reserved']
                # Share the remaining write allowance across I/O conditions so
                # the first fast filesystem loop cannot consume the whole run.
                checkpoints_per_run = int(available/max(1,remaining_io)/(2*args.pairs*size))
                if checkpoints_per_run<1:
                    raise BudgetExhausted('Not enough logical-write budget to sample remaining I/O conditions')
                budget_steps = checkpoints_per_run*(args.checkpoint_every if mode=='integrated' else 1)
                if steps>budget_steps:
                    steps = budget_steps
                    condition['io_budget_step_cap'] = steps
                    print(f'{name}: {steps} iterations fit the shared I/O budget; target duration may be shorter',flush=True)
            condition.update(steps=steps,calibrations=calibrations,status='measuring')
            # Exactly balanced AB/BA ordering for an even requested pair count.
            orders = [('full','reference'),('reference','full')]*(args.pairs//2)
            rng.shuffle(orders)
            condition['planned_order'] = orders
            estimated_pair = 2*(seconds*steps/initial_steps+max(v['process_elapsed_seconds']-v['loop_seconds'] for v in calibrations.values())+5)
            for pair,order in enumerate(orders):
                if time.monotonic()+estimated_pair > deadline:
                    condition['status'] = 'budget_exhausted_partial'
                    manifest['status'] = 'budget_exhausted_partial'; break
                checkpoint_count = math.ceil(steps/min(steps,args.checkpoint_every)) if mode=='integrated' else steps
                if manifest['logical_write_bytes_reserved']+2*size*checkpoint_count>args.max_written_gib*1024**3:
                    raise BudgetExhausted('Not enough logical-write budget for another complete pair')
                record = {'pair':pair,'order':order,'status':'running','results':{}}
                condition['pairs'].append(record); save(out/'manifest.json',manifest)
                for arm in order:
                    print(f'{name}: pair {pair+1}/{args.pairs}, {arm}, {steps} iterations',flush=True)
                    record['results'][arm] = execute(arm,steps,f'pair-{pair:03d}-{arm}')
                    save(out/'manifest.json',manifest)
                record['status'] = 'passed'; save(out/'manifest.json',manifest)
            if manifest['status']=='budget_exhausted_partial':
                break
            condition['status'] = 'passed'
            save(out/'manifest.json',manifest)
            report(out)
        if all(c['status']=='passed' for c in manifest['conditions']):
            manifest['status'] = 'finished'
        return out
    except BudgetExhausted as error:
        manifest['status'] = 'budget_exhausted_partial'
        for condition in manifest['conditions']:
            if condition['status'] in ('calibrating','measuring'):
                condition['status'] = 'budget_exhausted_partial'
        print(str(error),flush=True)
        return out
    except BaseException:
        manifest['status'] = 'failed_or_interrupted'
        for condition in manifest['conditions']:
            if condition['status'] in ('calibrating','measuring'):
                condition['status'] = 'failed_or_interrupted'
        raise
    finally:
        manifest['elapsed_seconds'] = time.monotonic()-started
        save(out/'manifest.json',manifest)
        report(out)
        print(f'Campaign status: {manifest["status"]}; evidence retained at {out}',flush=True)


def main(driver, argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--nodes',default='2',help='Comma-separated node scales, e.g. 2,4,8')
    parser.add_argument('--ranks-per-node',default='16',help='Positive counts or all, e.g. 16,32,all')
    parser.add_argument('--hosts',help='Optional ordered subset of allocation hosts')
    parser.add_argument('--groups-per-scale',type=int,default=1,help='Bounded rotated host groups per node scale')
    parser.add_argument('--workloads',default=','.join(MODES))
    parser.add_argument('--shape',help='Fixed global FFT dimensions nx,ny,nz; default balanced volume/rank')
    parser.add_argument('--fft-mib-per-rank',type=float,default=8)
    parser.add_argument('--io-mib-per-rank',type=float,default=8)
    parser.add_argument('--checkpoint-every',type=int,default=4)
    parser.add_argument('--pairs',type=int,default=10)
    parser.add_argument('--target-seconds',type=float,default=30)
    parser.add_argument('--max-steps',type=int,default=512)
    parser.add_argument('--budget-minutes',type=float,default=120)
    parser.add_argument('--timeout',type=int,default=300)
    parser.add_argument('--memory-fraction',type=float,default=.25)
    parser.add_argument('--max-checkpoint-gib',type=float,default=8)
    parser.add_argument('--max-written-gib',type=float,default=1024)
    parser.add_argument('--seed',type=int,default=16016)
    parser.add_argument('--slurm-overlap',action='store_true')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--reserved-cpus',help='Operator-verified OS CPU reservation, or none on a system without WEKA')
    group.add_argument('--reservations',help='Private JSON mapping each short hostname to verified OS CPU reservation')
    parser.add_argument('--audit-only',action='store_true')
    parser.add_argument('--report',type=Path,help='Regenerate CSV/HTML locally; no scheduler or build required')
    args = parser.parse_args(argv)
    if args.report:
        report(args.report.expanduser().resolve()); return
    try:
        args.nodes = list(dict.fromkeys(map(int,args.nodes.split(','))))
        args.ranks_per_node = list(dict.fromkeys(args.ranks_per_node.split(',')))
        args.workloads = list(dict.fromkeys(args.workloads.split(',')))
        args.shape = list(map(int,args.shape.split(','))) if args.shape else None
        if min(args.nodes)<1 or args.groups_per_scale<1 or any(v!='all' and int(v)<1 for v in args.ranks_per_node):
            raise ValueError('Node/rank counts must be positive')
        if not set(args.workloads)<=set(MODES):
            raise ValueError('Unknown workload')
        if args.shape and (len(args.shape)!=3 or min(args.shape)<2):
            raise ValueError('Shape needs three dimensions of at least two')
        if args.io_mib_per_rank*1024**2<8:
            raise ValueError('I/O volume must contain at least one double per rank')
        if args.pairs<2 or args.pairs%2 or not 1<=args.checkpoint_every<=args.max_steps<=10000:
            raise ValueError('Use an even pair count >=2 and 1 <= checkpoint-every <= max-steps <=10000')
        if not 0<args.memory_fraction<=.75 or not 5<=args.timeout<=3600:
            raise ValueError('Memory fraction must be (0,.75]; timeout must be 5..3600 seconds')
        for value in (args.fft_mib_per_rank,args.io_mib_per_rank,args.target_seconds,args.budget_minutes,
                      args.max_checkpoint_gib,args.max_written_gib):
            if not math.isfinite(value) or value<=0:
                raise ValueError('Sizes, duration and storage budgets must be finite and positive')
    except ValueError as error:
        parser.error(str(error))
    with (driver.HERE/'lock').open('a') as lock:
        try:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('A trial command is active; start production after it finishes') from None
        campaign(driver,args)
