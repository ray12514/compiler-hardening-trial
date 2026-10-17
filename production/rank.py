"""Pin a rank to its audited OS CPU, verify libraries, then exec the caller."""

import json
import hashlib
import os
from pathlib import Path
import re
import resource
import socket
import subprocess
import sys

from placement import cpus, job_cgroup, weka_resources, weka_masks, topology


def libraries(text, family, prefix):
    paths = re.findall(family + r'\S*\s+=>\s+(\S+)', text)
    if 'not found' in text or not paths or any(not p.startswith(str(prefix)+'/lib/') for p in paths):
        raise RuntimeError(f'Missing/mixed {family} dependency; expected {prefix}/lib')
    return paths


def allowed_cpus(layout, row):
    try:
        _, allowed, _ = job_cgroup(os.environ['SLURM_JOB_ID'])
    except RuntimeError:
        proof = row.get('binding_proof') or {}
        if (row.get('allocation_source')!='slurm-full-capacity-task-binding'
            or layout.get('job_id')!=os.environ['SLURM_JOB_ID']
            or proof.get('cpus_per_task')!=len(row.get('allowed_cpus',[]))
            or 'task/affinity' not in proof.get('task_plugin','').split(',')
            or proof.get('binding_type') not in ('threads','mask_cpu')
            or not proof.get('step_id','').isdigit()):
            raise
        allowed = set(row['allowed_cpus'])
    return allowed


def main():
    layout_path, evidence_path, binary, *arguments = sys.argv[1:]
    layout = json.loads(Path(layout_path).read_text())
    host = socket.gethostname().split('.')[0]
    rank, local = int(os.environ['OMPI_COMM_WORLD_RANK']), int(os.environ['OMPI_COMM_WORLD_LOCAL_RANK'])
    print(f'PRODUCTION_STAGE rank={rank} stage=wrapper-start', file=sys.stderr, flush=True)
    row = layout['hosts'][host]
    if int(os.environ['OMPI_COMM_WORLD_LOCAL_SIZE']) != layout['ranks_per_node']:
        raise RuntimeError('Wrong local rank count')
    cpu = row['cpus'][local]
    allowed = allowed_cpus(layout,row)
    forbidden = set(row['excluded_cpus'])
    for item in row['reservation_evidence']:
        current = cpus(Path(item['path']).read_text())
        if current != set(item['cpus']):
            raise RuntimeError('WEKA reservation changed since inventory; repeat qualification')
    if local==0 and row.get('reservation_source')=='weka-cgroup/local-resources':
        current_resources = weka_resources()
        online,_ = topology()
        try:
            current_mask,_ = weka_masks(online)
        except RuntimeError:
            if not current_resources:
                raise
            current_mask = set()
        if current_mask|current_resources != set(row['reserved']):
            raise RuntimeError('WEKA resource assignments changed; repeat qualification')
    if cpu not in allowed or cpu in forbidden:
        raise RuntimeError('CPU is no longer granted or intersects a service reservation')
    os.sched_setaffinity(0, {cpu})
    observed = sorted(os.sched_getaffinity(0))
    if observed != [cpu]:
        raise RuntimeError('Requested CPU binding was not applied')
    env = os.environ.copy()
    for name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
                 'BLIS_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS'):
        env[name] = '1'
    mpi, ucx = Path(env['TRIAL_MPI_PREFIX']), Path(env['TRIAL_UCX_PREFIX'])
    binary_hash = hashlib.sha256(Path(binary).read_bytes()).hexdigest()
    if env.get('TRIAL_PRODUCTION_CALLER_SHA256') != binary_hash:
        raise RuntimeError('Caller executable changed between controller and rank startup')
    loaded = subprocess.check_output(['ldd', binary], env=env, text=True, timeout=15)
    component = subprocess.check_output(['ldd', str(mpi/'lib/openmpi/mca_pml_ucx.so')],
                                        env=env, text=True, timeout=15)
    loaded_paths = libraries(loaded, r'lib(?:mpi|open-rte|open-pal)', mpi)
    loaded_paths += libraries(component, r'lib(?:ucp|uct|ucs|ucm)', ucx)
    payload = env.get('TRIAL_PRODUCTION_PAYLOAD','workflow')
    if payload not in ('workflow','osu'):
        raise RuntimeError('Unknown production payload')
    packages = ((r'libfftw3','fftw-mpi'),(r'libhdf5','hdf5-mpi')) if payload=='workflow' else ()
    for family, package in packages:
        loaded_paths += libraries(loaded, family, Path(env['TRIAL_ROOT'])/'install'/package/env['TRIAL_PRODUCTION_ARM'])
    if env.get('TRIAL_PRODUCTION_QUALIFY') == '1':
        output = subprocess.check_output([str(ucx/'bin/ucx_info'), '-d'], env=env, text=True, timeout=20)
        if not re.search(r'Transport:\s*rc_(?:mlx5|verbs)\b', output):
            raise RuntimeError('No RC transport on this node; TCP cannot qualify')
        (Path(evidence_path)/f'ucx-rank-{rank}.log').write_text(output)
    info = {'rank': rank, 'local_rank': local, 'host': host, 'cpus': observed,
            'allocation_source':row.get('allocation_source','slurm-job-cgroup'),
            'mpi_prefix': str(mpi), 'ucx_prefix': str(ucx),
            'binary_sha256':binary_hash,'loaded_library_paths':loaded_paths,
            'memlock_bytes': resource.getrlimit(resource.RLIMIT_MEMLOCK)}
    (Path(evidence_path)/f'rank-{rank}.json').write_text(json.dumps(info)+'\n')
    env['TRIAL_PRODUCTION_MEMORY_BYTES'] = str(layout['hosts'][host]['memory_budget_bytes']//layout['ranks_per_node'])
    print(f'PRODUCTION_STAGE rank={rank} stage=bound-and-verified', file=sys.stderr, flush=True)
    os.execve(binary, [binary, *arguments], env)


if __name__ == '__main__':
    main()
