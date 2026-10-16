"""Read-only Linux/Slurm CPU inventory and explicit physical-core placement.

CPU numbers in this module are Linux OS CPU IDs, never hwloc logical indexes.
"""

import argparse
import itertools
import json
import os
from pathlib import Path
import re
import socket
import shutil
import subprocess
import platform


def cpus(text):
    result = set()
    for item in text.strip().split(','):
        if not item:
            continue
        if not re.fullmatch(r'\d+(?:-\d+)?', item):
            raise ValueError('Expected an OS CPU list, such as 0-18,23-95')
        ends = list(map(int, item.split('-')))
        lo, hi = ends[0], ends[-1]
        if not 0 <= lo <= hi <= 1048575:
            raise ValueError('Invalid CPU range')
        result.update(range(lo, hi + 1))
    return result


def effective(directory):
    for name in ('cpuset.cpus.effective', 'cpuset.effective_cpus'):
        path = directory / name
        if path.exists():
            return cpus(path.read_text()), path
    raise RuntimeError(f'No effective cpuset at {directory}; cannot verify job CPU grant')


def job_cgroup(job, proc=Path('/proc'), mounts=None):
    """Locate the job ancestor, not the one-task audit step or shell affinity."""
    rows = (proc / 'self/cgroup').read_text().splitlines()
    for row in rows:
        _, controllers, relative = row.split(':', 2)
        if controllers and 'cpuset' not in controllers.split(','):
            continue
        parts = Path(relative).parts[1:]
        for i, part in enumerate(parts):
            if re.fullmatch(r'(?:job_?|slurm-job_)'+re.escape(job)+r'(?:\.(?:scope|slice))?',part):
                ancestor = Path('/').joinpath(*parts[:i+1])
                if mounts is not None:
                    base = mounts / 'cpuset' if controllers else mounts
                    directory = base.joinpath(*parts[:i+1])
                else:
                    directory = None
                    for mount in (proc/'self/mountinfo').read_text().splitlines():
                        left,_,right = mount.partition(' - ')
                        fields, kind = left.split(), right.split()
                        if not kind or (kind[0]!='cgroup2' if not controllers else
                                        kind[0]!='cgroup' or 'cpuset' not in kind[2].split(',')):
                            continue
                        unescape = lambda value: re.sub(r'\\([0-7]{3})',lambda m:chr(int(m[1],8)),value)
                        root,point = Path(unescape(fields[3])),Path(unescape(fields[4]))
                        if ancestor.is_relative_to(root):
                            directory = point/ancestor.relative_to(root)
                            break
                    if directory is None:
                        raise RuntimeError('Job cgroup is not visible in this mount namespace')
                mask, path = effective(directory)
                if not mask:
                    raise RuntimeError('Job effective cpuset is empty')
                return directory, mask, path
    raise RuntimeError('Cannot locate this Slurm job cgroup. No CPU grant inferred from the shell. '
                       'Check site cgroup support before the dense campaign.')


def allocation_grant(expected=None):
    """Prefer the job cpuset; otherwise accept only a dedicated Slurm-bound audit task."""
    try:
        directory,mask,path = job_cgroup(os.environ['SLURM_JOB_ID'])
        return {'directory':directory,'allowed':sorted(mask),'path':str(path),
                'source':'slurm-job-cgroup','binding_proof':None}
    except RuntimeError:
        if expected is None:
            raise
    kind = os.environ.get('SLURM_CPU_BIND_TYPE','').strip().split(':')[0]
    mask = sorted(os.sched_getaffinity(0))
    if (expected<1 or os.environ.get('SLURM_CPUS_PER_TASK')!=str(expected)
        or not os.environ.get('SLURM_STEP_ID','').isdigit()
        or os.environ.get('SLURM_LOCALID')!='0'
        or 'task/affinity' not in os.environ.get('TRIAL_PRODUCTION_TASK_PLUGIN','').split(',')
        or kind not in ('threads','mask_cpu') or len(mask)!=expected):
        raise RuntimeError('Cannot verify a full-capacity Slurm task binding. The inventory task '
                           'must receive the requested allocated CPU count with task/affinity and '
                           'thread binding. Shell affinity and online CPU counts were not used as a grant.')
    return {'directory':None,'allowed':mask,'path':None,
            'source':'slurm-full-capacity-task-binding',
            'binding_proof':{'step_id':os.environ['SLURM_STEP_ID'],'cpus_per_task':expected,
                             'task_plugin':os.environ['TRIAL_PRODUCTION_TASK_PLUGIN'],
                             'binding_type':kind}}


def topology(base=Path('/sys/devices/system/cpu')):
    online = cpus((base / 'online').read_text())
    rows = {}
    for cpu in sorted(online):
        path = base / f'cpu{cpu}'
        node = list(path.glob('node[0-9]*'))
        rows[cpu] = {
            'socket': int((path/'topology/physical_package_id').read_text()),
            'core': int((path/'topology/core_id').read_text()),
            'numa': int(node[0].name[4:]) if node else -1,
            'siblings': sorted(cpus((path/'topology/thread_siblings_list').read_text())),
        }
    return online, rows


def resource_cpus(text):
    """Parse only the documented ROLES / NODE ID / CORE ID table, never networking."""
    result = set()
    active = False
    for line in text.splitlines():
        if re.fullmatch(r'\s*ROLES\s+NODE ID\s+CORE ID\s*',line):
            active = True
            continue
        if active:
            if not line.strip() or line.lstrip().startswith('NET DEVICE'):
                break
            match = re.fullmatch(r'\s*[A-Z_]+\s+\d+\s+(\d+)\s*',line)
            if match:
                result.add(int(match[1]))
    return result


def weka_resources():
    binary = shutil.which('weka')
    if not binary:
        return set()
    try:
        result = subprocess.run([binary,'local','resources'],capture_output=True,text=True,timeout=10)
    except (OSError,subprocess.TimeoutExpired):
        return set()
    return resource_cpus(result.stdout) if result.returncode==0 else set()


def weka_masks(online, mounts=Path('/sys/fs/cgroup')):
    """Only accept narrow masks under WEKA-named cgroups; broad inheritance is ambiguous."""
    evidence = []
    # Bounded walk; do not traverse every task's cgroup on a busy cluster.
    for parent, dirs, files in os.walk(mounts):
        path = Path(parent)
        parts = path.relative_to(mounts).parts
        named = any('weka' in part.lower() for part in parts)
        dirs[:] = [d for d in dirs if not d.startswith(('job_', 'step_', 'user-'))]
        if len(parts) >= 6:
            dirs[:] = []
        if not named:
            continue
        for name in ('cpuset.cpus.effective', 'cpuset.effective_cpus', 'cpuset.cpus'):
            if name not in files:
                continue
            file = path / name
            mask = cpus(file.read_text()) & online
            if mask and mask != online:
                evidence.append({'path': str(file), 'cpus': sorted(mask)})
    if not evidence:
        raise RuntimeError('No unambiguous WEKA CPU reservation found. Inspect the local WEKA '
                           'client cgroup/resource assignments, then supply --reserved-cpus '
                           'with the verified OS CPU IDs (or a per-host --reservations JSON). '
                           'No guessed CPU range was used.')
    return set().union(*(set(row['cpus']) for row in evidence)), evidence


def memory_available(job_dir, proc=Path('/proc')):
    text = (proc / 'meminfo').read_text()
    match = re.search(r'^MemAvailable:\s+(\d+) kB', text, re.M)
    if not match:
        raise RuntimeError('MemAvailable is missing')
    limits = [int(match[1]) * 1024]
    # For cgroup v2 the job ancestor gives the job memory envelope. For v1,
    # use its corresponding memory-controller directory if present.
    memory_dir = job_dir or Path('/sys/fs/cgroup')
    if job_dir is not None and '/cpuset/' in str(job_dir):
        memory_dir = Path(str(job_dir).replace('/cpuset/', '/memory/', 1))
    for directory in (memory_dir, *memory_dir.parents):
        for limit, used in (('memory.max', 'memory.current'),
                            ('memory.limit_in_bytes', 'memory.usage_in_bytes')):
            file = directory / limit
            if file.is_file() and file.read_text().strip().isdigit():
                value = int(file.read_text())
                consumption = int((directory/used).read_text())
                limits.append(max(0, value-consumption))
    return min(limits)


def inventory(reserved=None):
    online, cores = topology()
    requested = os.environ.get('TRIAL_PRODUCTION_ALLOCATION_CPUS')
    grant = allocation_grant(int(requested) if requested else None)
    if reserved is None:
        resource_ids = weka_resources()
        try:
            excluded, evidence = weka_masks(online)
        except RuntimeError:
            if not resource_ids:
                raise
            excluded, evidence = set(), []
        excluded |= resource_ids
        source = 'weka-cgroup/local-resources'
    else:
        excluded = cpus(reserved) if reserved != 'none' else set()
        evidence = []
        source = 'operator-verified-os-cpu-list'
        resource_ids = set()
    if excluded - online:
        raise RuntimeError('Reservation includes unknown/offline CPU IDs; verify the OS numbering')
    model = re.search(r'^(?:model name|Processor|Hardware)\s*:\s*(.+)$',Path('/proc/cpuinfo').read_text(),re.M)
    hardware = {'architecture':platform.machine(),'model':model[1] if model else 'unknown',
                'online_cpu_count':len(online),
                'physical_core_count':len({(v['socket'],v['core']) for v in cores.values()})}
    return {'host': socket.gethostname().split('.')[0], 'job_id': os.environ['SLURM_JOB_ID'],
            'hardware':hardware,
            'online': sorted(online), 'allowed': grant['allowed'],
            'allocation_source':grant['source'],'binding_proof':grant['binding_proof'],
            'job_cpuset_file': grant['path'], 'reserved': sorted(excluded),
            'reservation_source': source, 'reservation_evidence': evidence,
            'weka_resource_cpus': sorted(resource_ids),
            'topology': cores, 'available_memory_bytes': memory_available(grant['directory'])}


def eligible(info):
    topo = {int(k): v for k, v in info['topology'].items()}
    forbidden = set(info['reserved'])
    for cpu in list(forbidden):
        forbidden.update(topo[cpu]['siblings'])
    allowed = (set(info['online']) & set(info['allowed'])) - forbidden
    physical = {}
    for cpu in sorted(allowed):
        row = topo[cpu]
        if set(row['siblings']) & forbidden:
            continue
        physical.setdefault((row['socket'], row['core']), cpu)
    # Round-robin NUMA groups; a prefix stays balanced as density increases.
    groups = {}
    for cpu in physical.values():
        row = topo[cpu]
        groups.setdefault((row['socket'], row['numa']), []).append(cpu)
    ordered = [cpu for group in itertools.zip_longest(*[groups[k] for k in sorted(groups)])
               for cpu in group if cpu is not None]
    return ordered, sorted(forbidden)


def make_layout(infos, hosts, rpn, cpu_counts, task_limit):
    available = {}
    for host in hosts:
        info = infos[host]
        candidates, forbidden = eligible(info)
        limit = min(len(candidates), cpu_counts[host])
        available[host] = {'eligible_cpus': candidates, 'excluded_cpus': forbidden,
                           'capacity': limit, 'job_cpuset_file': info['job_cpuset_file'],
                           'allowed_cpus':info['allowed'],
                           'allocation_source':info.get('allocation_source','slurm-job-cgroup'),
                           'binding_proof':info.get('binding_proof'),
                           'reservation_evidence': info['reservation_evidence'],
                           'reservation_source': info.get('reservation_source','operator-verified-os-cpu-list'),
                           'weka_resource_cpus': info.get('weka_resource_cpus',[]),
                           'reserved': info['reserved']}
    count = min(min(v['capacity'] for v in available.values()),task_limit//len(hosts)) if rpn == 'all' else int(rpn)
    if count < 1 or count*len(hosts) > task_limit:
        raise RuntimeError('Requested layout exceeds the verified job task capacity')
    for host, row in available.items():
        if count > row['capacity']:
            raise RuntimeError(f'{host}: requested {count} ranks, but only {row["capacity"]} '
                               'physical cores fit both the allocation and service exclusions')
        row['cpus'] = row['eligible_cpus'][:count]
    return {'ranks_per_node': count, 'hosts': available}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path)
    parser.add_argument('--show-weka',action='store_true',help='Print only discovered service CPU IDs; no Slurm job needed')
    parser.add_argument('--reserved-cpus')
    parser.add_argument('--reservations', type=Path)
    args = parser.parse_args()
    if args.show_weka:
        online,_ = topology()
        resource_ids = weka_resources()
        try:
            mask,_ = weka_masks(online)
        except RuntimeError:
            if not resource_ids:
                raise
            mask = set()
        print(json.dumps({'weka_os_cpus':sorted(mask|resource_ids)},indent=2))
        return
    if args.out is None:
        parser.error('--out is required for allocation inventory')
    reserved = args.reserved_cpus
    if args.reservations:
        values = json.loads(args.reservations.read_text())
        host = socket.gethostname().split('.')[0]
        if host not in values:
            raise RuntimeError('No verified reservation for this host in --reservations')
        reserved = values[host]
    info = inventory(reserved)
    path = args.out / f'{info["host"]}.json'
    path.write_text(json.dumps(info, indent=2)+'\n')


if __name__ == '__main__':
    main()
