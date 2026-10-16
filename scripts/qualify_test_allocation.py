"""Qualify local and inter-node MPI communication; do not run performance timings."""

import argparse
from collections import Counter
import datetime
import fcntl
import json
import os
from pathlib import Path
import re
import resource
import socket
import subprocess
import sys
import tempfile

from collect_mpi_diagnostics import activated_env, allocation_context, rdma_ports, run, selected_env
from probe_mpi_startup import run_logged


SOURCE = r'''#include <mpi.h>
#include <stdio.h>
#include <stdlib.h>
int main(int argc, char **argv) {
    int rank, size, n; char host[MPI_MAX_PROCESSOR_NAME];
    MPI_Init(&argc, &argv);
    MPI_Comm_rank(MPI_COMM_WORLD, &rank); MPI_Comm_size(MPI_COMM_WORLD, &size);
    MPI_Get_processor_name(host, &n);
    const int count=131072; /* 512 KiB: exercise more than startup/control messages */
    int *send=malloc(count*sizeof(int)), *recv=malloc(count*sizeof(int));
    if (!send || !recv) MPI_Abort(MPI_COMM_WORLD, 1);
    for (int i=0; i<count; i++) send[i]=rank+i;
    int previous=(rank+size-1)%size, next=(rank+1)%size;
    MPI_Sendrecv(send,count,MPI_INT,next,42,recv,count,MPI_INT,previous,42,
                 MPI_COMM_WORLD,MPI_STATUS_IGNORE);
    int good=1, total;
    for (int i=0; i<count; i++) if (recv[i]!=previous+i) good=0;
    MPI_Allreduce(&good,&total,1,MPI_INT,MPI_SUM,MPI_COMM_WORLD);
    if (total!=size) MPI_Abort(MPI_COMM_WORLD, 1);
    free(send); free(recv);
    printf("QUALIFICATION rank=%d size=%d host=%s PASS\n",rank,size,host);
    fflush(stdout);
    MPI_Finalize(); return 0;
}
'''


def require_libraries(output, family, prefix):
    paths = re.findall(family + r'\S*\s+=>\s+(\S+)', output)
    if 'not found' in output or not paths or any(not p.startswith(str(prefix) + '/lib/') for p in paths):
        raise RuntimeError(f'Missing or mixed libraries for {family}; expected {prefix}/lib')


def rank_check(binary, destination, hosts):
    """Executed on every rank before MPI_Init; then replace Python with the caller."""
    rank = os.environ['OMPI_COMM_WORLD_RANK']
    mpi, ucx = Path(os.environ['TRIAL_MPI_PREFIX']), Path(os.environ['TRIAL_UCX_PREFIX'])
    host = socket.gethostname()
    if host.split('.')[0] not in {h.split('.')[0] for h in hosts.split(',')}:
        raise RuntimeError('Rank started outside the selected hosts')
    evidence = {'rank': int(rank), 'host': host, 'mpi_prefix': str(mpi), 'ucx_prefix': str(ucx),
                'runtime_settings': selected_env(os.environ), 'ports': rdma_ports(),
                'allowed_cpus': sorted(os.sched_getaffinity(0)),
                'memlock_bytes': resource.getrlimit(resource.RLIMIT_MEMLOCK), 'commands': {}}
    for label, command in (
        ('caller_libraries', ['ldd', str(binary)]),
        ('launcher_libraries', ['ldd', str(mpi / 'bin/mpirun')]),
        ('pml_libraries', ['ldd', str(mpi / 'lib/openmpi/mca_pml_ucx.so')]),
        ('ucx_devices', [str(ucx / 'bin/ucx_info'), '-d']),
    ):
        result = run(command, env=os.environ.copy())
        evidence['commands'][label] = result
        if result['returncode'] != 0:
            raise RuntimeError(f'{label} failed: {result["stderr"]}')
    for label in ('caller_libraries', 'launcher_libraries'):
        require_libraries(evidence['commands'][label]['stdout'], r'lib(?:mpi|open-rte|open-pal)', mpi)
    require_libraries(evidence['commands']['pml_libraries']['stdout'], r'lib(?:ucp|uct|ucs|ucm)', ucx)
    if not re.search(r'Transport:\s*rc_(?:mlx5|verbs)\b', evidence['commands']['ucx_devices']['stdout']):
        raise RuntimeError('No RC transport available on this rank; RDMA qualification cannot pass')
    (destination / f'rank-{rank}.json').write_text(json.dumps(evidence, indent=2) + '\n')
    os.execve(str(binary), [str(binary)], os.environ.copy())


def validate_runtime(env):
    # An allow-list prevents a successful TCP fallback from passing this check.
    transports = set(env.get('UCX_TLS', '').split(','))
    rc = {'rc', 'rc_mlx5', 'rc_verbs'}
    if not transports.intersection(rc) or not transports <= rc | {'sm', 'self'}:
        raise RuntimeError('Qualification requires the saved UCX_TLS to select RC plus optional sm/self, '
                           'for example rc,sm,self. No runtime settings were changed.')


def check_placement(output, hosts, ranks_per_node):
    rows = re.findall(r'^QUALIFICATION rank=(\d+) size=(\d+) host=(\S+) PASS$', output, re.M)
    count = len(hosts) * ranks_per_node
    if len(rows) != count or {int(row[0]) for row in rows} != set(range(count)):
        raise RuntimeError('Missing/duplicate rank completion evidence')
    expected = Counter({h.split('.')[0]: ranks_per_node for h in hosts})
    if any(int(row[1]) != count for row in rows) or Counter(row[2].split('.')[0] for row in rows) != expected:
        raise RuntimeError('Ranks did not use the selected hosts/layout')


def qualify(root, hosts, ranks_per_node, timeout, slurm_overlap=False):
    parent = root / 'results/diagnostics'
    parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = Path(tempfile.mkdtemp(prefix=f'mpi-allocation-{stamp}-', dir=parent))
    print(f'Qualification evidence: {out}', flush=True)
    report = {'qualification_only': True, 'job_id': os.environ['SLURM_JOB_ID'], 'hosts': hosts,
              'allocation': allocation_context(),
              'job': run(['scontrol', 'show', 'job', os.environ['SLURM_JOB_ID']], timeout=10),
              'ranks_per_node': ranks_per_node, 'slurm_overlap_requested': slurm_overlap,
              'arms': {}, 'passed': False,
              'scope': 'Selected hosts/layout only; no overhead estimate or whole-allocation qualification.'}
    previous = None
    try:
        for arm in ('full', 'reference'):
            env, note = activated_env(root, arm)
            if env is None:
                raise RuntimeError(note)
            if slurm_overlap:
                # Open MPI 4.1.x appends plm_slurm_args to its actual srun command.
                # Sharing an interactive shell's Slurm step does not authorize
                # extra MPI ranks per core; retain binding/nooversubscribe below.
                arguments = env.get('OMPI_MCA_plm_slurm_args', '').split()
                if '--overlap' not in arguments:
                    arguments.append('--overlap')
                env['OMPI_MCA_plm_slurm_args'] = ' '.join(arguments)
            validate_runtime(env)
            settings = selected_env(env)
            comparable = {k: v for k, v in settings.items() if k not in ('UCX_LOG_LEVEL', 'TRIAL_MPI_TUNING')}
            if previous is not None and comparable != previous:
                raise RuntimeError('Full/reference runtime settings differ; retain evidence and resolve before timing')
            previous = comparable
            mpi, ucx = Path(env['MPI_PREFIX']), Path(env.pop('UCX_PREFIX'))
            env.update(TRIAL_MPI_PREFIX=str(mpi), TRIAL_UCX_PREFIX=str(ucx),
                       UCX_LOG_LEVEL='info', OMPI_MCA_pml='ucx')
            folder = out / arm
            folder.mkdir()
            source, binary = folder / 'communication.c', folder / 'communication'
            source.write_text(SOURCE)
            result = {'mpi_prefix': str(mpi), 'ucx_prefix': str(ucx),
                      'runtime_settings': selected_env(env), 'cases': []}
            report['arms'][arm] = result
            result['compile'] = run_logged([str(mpi / 'bin/mpicc'), '-O0', str(source), '-o', str(binary)],
                                           env, folder / 'compile.log', timeout)
            if result['compile']['returncode'] != 0 or result['compile']['timed_out']:
                raise RuntimeError(f'{arm}: qualification caller compilation failed; see {folder / "compile.log"}')
            # Two ranks locally exercise shared memory; the cross-node lane uses the requested layout.
            for label, selected, rpn in (('local', hosts[:1], max(2, ranks_per_node)),
                                         ('inter-node', hosts, ranks_per_node)):
                case_dir = folder / label
                case_dir.mkdir()
                command = [str(mpi / 'bin/mpirun'), '-np', str(len(selected) * rpn),
                           '--host', ','.join(f'{h}:{rpn}' for h in selected),
                           '--map-by', f'ppr:{rpn}:node', '--bind-to', 'core', '--report-bindings',
                           '--nooversubscribe', '--mca', 'pml', 'ucx']
                for name in ('btl', 'mtl', 'plm', 'ras', 'plm_slurm_args'):
                    if 'OMPI_MCA_' + name in env:
                        command += ['--mca', name, env['OMPI_MCA_' + name]]
                for name in ('PATH', 'LD_LIBRARY_PATH', 'TRIAL_MPI_PREFIX', 'TRIAL_UCX_PREFIX', 'UCX_LOG_LEVEL'):
                    command += ['-x', name]
                for name in sorted(env):
                    if name.startswith('UCX_') and name != 'UCX_LOG_LEVEL':
                        command += ['-x', name]
                command += [sys.executable, str(Path(__file__).resolve()), '--rank', str(binary),
                            str(case_dir), ','.join(selected)]
                print(f'{arm}: {label}, hosts={",".join(selected)}, ranks/node={rpn}', flush=True)
                case = run_logged(command, env, case_dir / 'communication.log', timeout)
                result['cases'].append(case)
                if case['returncode'] != 0 or case['timed_out']:
                    raise RuntimeError(f'{arm}/{label}: failed or timed out; inspect {case["log"]}. '
                                       'Do not mask missing slots/cores with oversubscription.')
                check_placement(Path(case['log']).read_text(errors='replace'), selected, rpn)
                if any(not (case_dir / f'rank-{rank}.json').is_file() for rank in range(len(selected) * rpn)):
                    raise RuntimeError('Rank library/transport inventory is incomplete')
        report['passed'] = True
        print('PASS: both stacks completed local and inter-node data checks with RC-only network selection.', flush=True)
    except BaseException as error:
        report['error'] = str(error)
        raise
    finally:
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
        print(f'Report: {out / "report.json"}', flush=True)
    return out


def main():
    if sys.argv[1:2] == ['--rank']:
        rank_check(Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4])
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trial-root', type=Path,
                        default=Path(os.environ.get('TRIAL_ROOT', str(Path.home() / 'COMPILER_HARDENING'))))
    parser.add_argument('--hosts', help='Comma-separated allocated hosts; default is the first two')
    parser.add_argument('--ranks-per-node', type=int, choices=(1, 4), default=1)
    parser.add_argument('--slurm-overlap', action='store_true',
                        help="Pass --overlap to Open MPI's srun steps when an interactive shell holds resources")
    parser.add_argument('--timeout', type=int, default=90, help='Seconds per compile/launch, 1-300')
    args = parser.parse_args()
    try:
        if not 1 <= args.timeout <= 300:
            raise RuntimeError('Choose --timeout between 1 and 300 seconds')
        root = args.trial_root.expanduser().resolve()
        if not os.environ.get('SLURM_JOB_ID') or not os.environ.get('SLURM_JOB_NODELIST'):
            raise RuntimeError('Run in the existing Slurm allocation; no new allocation will be requested')
        hosts = subprocess.check_output(['scontrol', 'show', 'hostnames', os.environ['SLURM_JOB_NODELIST']],
                                        text=True, timeout=10).split()
        selected = args.hosts.split(',') if args.hosts else hosts[:2]
        if (len(selected) < 2 or len(set(h.split('.')[0] for h in selected)) != len(selected)
                or any(h not in hosts or not re.fullmatch(r'[A-Za-z0-9_.-]+', h) for h in selected)):
            raise RuntimeError('Select at least two distinct hosts from this allocation')
        if socket.gethostname().split('.')[0] not in {h.split('.')[0] for h in hosts}:
            raise RuntimeError('Enter an allocated compute-node shell first')
        print(f'Allocated hosts: {",".join(hosts)}\nSelected hosts: {",".join(selected)}', flush=True)
        if args.slurm_overlap:
            print('Slurm step overlap enabled; MPI ranks remain core-bound with --nooversubscribe.', flush=True)
        with (root / 'runner/lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError('A trial command is active; wait for it to finish') from None
            qualify(root, selected, args.ranks_per_node, args.timeout, args.slurm_overlap)
    except (RuntimeError, OSError, KeyError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, f'ERROR: {error}\n')


if __name__ == '__main__':
    main()
