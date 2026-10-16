"""Check allocation qualification orchestration without a scheduler or RDMA hardware."""

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_mpi_driver import REPO, executable

with patch.object(sys, 'path', [str(REPO / 'scripts'), *sys.path]):
    spec = importlib.util.spec_from_file_location('allocation_check', REPO / 'scripts/qualify_test_allocation.py')
    qualification = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(qualification)


class AllocationTests(unittest.TestCase):
    def fixture(self, root, fail=False):
        (root / 'runner/state').mkdir(parents=True)
        (root / 'runner/state/fftw-full.json').write_text('keep build evidence')
        envs = {}
        for arm in ('full', 'reference'):
            mpi = root / arm
            executable(mpi / 'bin/mpicc', '''while test "$#" -gt 0; do
if test "$1" = -o; then shift; touch "$1"; exit 0; fi
shift
done
exit 1
''')
            executable(mpi / 'bin/mpirun', '''test -z "${UCX_PREFIX+x}"
test "$UCX_TLS" = rc,sm,self
case " $* " in *' --mca btl ^uct,openib,ofi '*) ;; *) exit 9;; esac
case " $* " in *' --nooversubscribe '*) ;; *) exit 9;; esac
case " $* " in *' --bind-to core '*) ;; *) exit 9;; esac
''' + ('echo "injected launch failure"; exit 7\n' if fail else '''python3 - "$@" <<'CODE'
import json,pathlib,sys
args=sys.argv[1:]
rpn=int(args[args.index('--map-by')+1].split(':')[1])
dest=pathlib.Path(args[-2]); hosts=args[-1].split(',')
rank=0
for host in hosts:
    for _ in range(rpn):
        (dest/f'rank-{rank}.json').write_text(json.dumps({'host':host}))
        print(f'QUALIFICATION rank={rank} size={len(hosts)*rpn} host={host} PASS')
        rank+=1
CODE
'''))
            envs[arm] = {**os.environ, 'MPI_PREFIX': str(mpi), 'UCX_PREFIX': str(root / f'ucx-{arm}'),
                         'UCX_TLS': 'rc,sm,self', 'OMPI_MCA_pml': 'ucx',
                         'OMPI_MCA_btl': '^uct,openib,ofi', 'OMPI_MCA_mtl': '^ofi'}
        return envs

    def test_both_arms_local_and_selected_nodes_keep_saved_settings_and_builds(self):
        for rpn in (1, 4):
            with self.subTest(rpn=rpn), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                envs = self.fixture(root)
                with patch.dict(os.environ, {'SLURM_JOB_ID': '123'}), \
                     patch.object(qualification, 'activated_env', side_effect=lambda root, arm: (envs[arm].copy(), 'saved')), \
                     contextlib.redirect_stdout(io.StringIO()):
                    out = qualification.qualify(root, ['node2', 'node7'], rpn, 3)
                report = json.loads((out / 'report.json').read_text())
                self.assertTrue(report['passed'])
                self.assertTrue(report['qualification_only'])
                for arm in ('full', 'reference'):
                    self.assertEqual(len(report['arms'][arm]['cases']), 2)
                    remote = report['arms'][arm]['cases'][1]['command']
                    self.assertIn(f'node2:{rpn},node7:{rpn}', remote)
                    self.assertNotIn('--oversubscribe', remote)
                self.assertEqual((root / 'runner/state/fftw-full.json').read_text(), 'keep build evidence')

    def test_failure_stops_before_reference_and_retains_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            envs = self.fixture(root, fail=True)
            with patch.dict(os.environ, {'SLURM_JOB_ID': '123'}), \
                 patch.object(qualification, 'activated_env', side_effect=lambda root, arm: (envs[arm].copy(), 'saved')), \
                 contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(RuntimeError, 'failed or timed out'):
                qualification.qualify(root, ['node2', 'node7'], 1, 3)
            path = next(root.glob('results/diagnostics/*/report.json'))
            report = json.loads(path.read_text())
            self.assertFalse(report['passed'])
            self.assertNotIn('reference', report['arms'])
            self.assertIn('injected launch failure', Path(report['arms']['full']['cases'][0]['log']).read_text())

    def test_tcp_fallback_and_mixed_dependencies_cannot_pass(self):
        for tls in ('', 'all', 'tcp,sm,self', 'rc,tcp,sm,self', '^tcp'):
            with self.subTest(tls=tls), self.assertRaisesRegex(RuntimeError, 'saved UCX_TLS'):
                qualification.validate_runtime({'UCX_TLS': tls})
        qualification.validate_runtime({'UCX_TLS': 'rc,sm,self'})
        with self.assertRaisesRegex(RuntimeError, 'mixed libraries'):
            qualification.require_libraries('libmpi.so => /usr/lib/libmpi.so', 'libmpi', '/private/mpi')

    def test_wrong_hosts_rank_counts_and_duplicate_ranks_are_rejected(self):
        good = 'QUALIFICATION rank=0 size=2 host=node2 PASS\nQUALIFICATION rank=1 size=2 host=node7 PASS\n'
        qualification.check_placement(good, ['node2', 'node7'], 1)
        for output in (good.replace('host=node7', 'host=node2'), good.replace('size=2', 'size=4'),
                       good.replace('rank=1', 'rank=0'), ''):
            with self.subTest(output=output), self.assertRaises(RuntimeError):
                qualification.check_placement(output, ['node2', 'node7'], 1)

    def test_rank_checks_private_libraries_and_records_evidence_before_exec(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env = {'OMPI_COMM_WORLD_RANK': '0', 'TRIAL_MPI_PREFIX': '/private/mpi',
                   'TRIAL_UCX_PREFIX': '/private/ucx', 'UCX_TLS': 'rc,sm,self'}
            def evidence(command, **kwargs):
                text = ('libmpi.so => /private/mpi/lib/libmpi.so' if 'communication' in command[-1]
                        or 'mpirun' in command[-1] else
                        'libucp.so => /private/ucx/lib/libucp.so' if 'pml_ucx' in command[-1] else
                        '# Transport: rc_mlx5\n# Device: mlx5_0:1\n')
                return {'command': command, 'returncode': 0, 'stdout': text, 'stderr': ''}
            with patch.dict(os.environ, env, clear=True), \
                 patch.object(qualification.socket, 'gethostname', return_value='node2'), \
                 patch.object(qualification.os, 'sched_getaffinity', return_value={4}, create=True), \
                 patch.object(qualification, 'run', side_effect=evidence), \
                 patch.object(qualification.os, 'execve') as execute:
                qualification.rank_check(Path('/shared/communication'), root, 'node2,node7')
                record = json.loads((root / 'rank-0.json').read_text())
                self.assertEqual(record['allowed_cpus'], [4])
                self.assertEqual(len(record['commands']), 4)
                execute.assert_called_once()


if __name__ == '__main__':
    unittest.main()
