"""Check the package pilot's coverage, exports and measurement-only refresh."""

import argparse
import contextlib
import csv
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_mpi_driver import driver_at


class PilotTests(unittest.TestCase):
    def summary(self, root, package, case):
        out = root / 'results/reframe' / package
        path = out / 'paired' / package / case / 'reference/summary.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({'case': case, 'scope': 'stack', 'comparator': 'reference',
            'primary_phase': 'execution', 'effective_profile_ids': ['complete-test'], 'phases': {
                'execution': {'pairs': 10, 'full_runtime_seconds_mean': 1.1,
                    'full_runtime_seconds_stdev': 0.02, 'comparator_runtime_seconds_mean': 1.0,
                    'comparator_runtime_seconds_stdev': 0.01, 'full_runtime_increase_percent': 10.0,
                    'bootstrap_95_percent_interval': [8.0, 12.0]}}}))
        return out

    def test_all_runs_each_package_and_exports_complete_primary_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            driver = driver_at(root)
            observed = []
            def run(args, entry):
                observed.append((args.package, args.mpi, args.ranks_per_node, args.slurm_overlap))
                name = entry['package']
                for case in entry['expected_workloads']:
                    out = self.summary(root, name, case)
                entry['result_dir'] = str(out.relative_to(root))
                return out
            args = argparse.Namespace(package='all', mpi=False, nodes=2, ranks_per_node=4,
                                      slurm_overlap=True, pairs=10)
            with patch.dict(os.environ, {'SLURM_JOB_ID': '123', 'SLURM_JOB_NODELIST': 'node[1-8]', 'IO_DIR': str(root/'io')}), \
                 patch.object(driver, 'require_setup'), patch.object(driver, 'check_reframe'), \
                 patch.object(driver, 'verify_test_tree'), \
                 patch.object(driver.subprocess, 'check_output', return_value='node1\nnode2\n'), \
                 patch.object(driver, 'test_one', side_effect=run), contextlib.redirect_stdout(io.StringIO()):
                driver.test(args)
            self.assertEqual([(p,m) for p,m,_,_ in observed],
                             [('fftw',False),('hdf5',False),('lapack',False),('fftw',True),('hdf5',True)])
            path = next(root.glob('results/pilots/*/pilot.json'))
            manifest = json.loads(path.read_text())
            self.assertEqual(manifest['status'], 'finished')
            self.assertTrue(manifest['coverage_complete'])
            with (path.parent/'phases.csv').open() as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), sum(len(v.split(',')) for v in driver.WORKLOADS.values()))
            self.assertEqual({r['package'] for r in rows}, set(driver.WORKLOADS))
            self.assertEqual({r['runtime_increase_percent'] for r in rows}, {'10.0'})
            self.assertEqual({r['ranks_per_node'] for r in rows if r['package'].endswith('-mpi')}, {'4'})

    def test_failed_pilot_preserves_partial_results_and_marks_remaining_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            driver = driver_at(root)
            args = argparse.Namespace(package='all', mpi=False, nodes=2, ranks_per_node=1, pairs=10)
            calls = []
            def run(args, entry):
                calls.append(entry['package'])
                if entry['package'] == 'hdf5': raise RuntimeError('package failed')
                out = self.summary(root, 'fftw', entry['expected_workloads'][0])
                entry['result_dir'] = str(out.relative_to(root))
            with patch.dict(os.environ, {'SLURM_JOB_ID': '123', 'SLURM_JOB_NODELIST': 'nodes', 'IO_DIR': str(root/'io')}), \
                 patch.object(driver, 'require_setup'), patch.object(driver, 'check_reframe'), \
                 patch.object(driver, 'verify_test_tree'), \
                 patch.object(driver.subprocess, 'check_output', return_value='node1\nnode2\n'), \
                 patch.object(driver, 'test_one', side_effect=run), contextlib.redirect_stdout(io.StringIO()), \
                 self.assertRaisesRegex(RuntimeError, 'package failed'):
                driver.test(args)
            self.assertEqual(calls, ['fftw', 'hdf5'])
            path = next(root.glob('results/pilots/*/pilot.json'))
            manifest = json.loads(path.read_text())
            self.assertFalse(manifest['coverage_complete'])
            self.assertEqual(manifest['status'], 'failed_or_interrupted')
            self.assertEqual(manifest['runs'][2]['status'], 'not_run_after_failure')
            self.assertTrue((path.parent/'phases.csv').is_file())

    def test_refresh_changes_only_measurement_identity_and_generated_scripts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            driver = driver_at(root)
            for name in ('bench','reframe'):
                (root/name).mkdir()
            (root/'env.sh').write_text('')
            (root/'profiles.sh').write_text('')
            policy = {'disabled': {}, 'events': []}
            qualification = {'identity': 'complete-test', 'policy': policy}
            driver.save(driver.HERE/'qualification.json', qualification)
            state = {'profile_recipe': driver.digest(driver.block('01-common',0)),
                     'measurement_recipes': 'old-measurements', 'qualification': qualification,
                     'env': driver.filehash(root/'env.sh'), 'site_env': None}
            driver.save(driver.HERE/'setup.json', state)
            driver.save(driver.HERE/'state/fftw-full.json', {'identity': 'retain-compiled-build'})
            before = (driver.HERE/'state/fftw-full.json').read_bytes()
            with patch.object(driver, 'qualify') as qualify, contextlib.redirect_stdout(io.StringIO()):
                driver.refresh_tests()
                qualify.assert_not_called()
            after = driver.require_setup()
            self.assertEqual({k:v for k,v in state.items() if k!='measurement_recipes'},
                             {k:v for k,v in after.items() if k!='measurement_recipes'})
            self.assertEqual((driver.HERE/'state/fftw-full.json').read_bytes(), before)
            self.assertTrue((root/'bench/paired.py').is_file())
            self.assertTrue((root/'reframe/hardening.py').is_file())

    def test_truncated_summary_does_not_hide_completed_rows_or_claim_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            driver = driver_at(root)
            session = self.summary(root,'fftw','fft-small')
            broken = session/'paired/fftw/fft-large/reference/summary.json'
            broken.parent.mkdir(parents=True)
            broken.write_text('{"case":')
            out = root/'results/pilots/partial'
            out.mkdir(parents=True)
            manifest = {'status':'finished','runs':[{'package':'fftw','nodes':1,'ranks_per_node':0,
                'expected_workloads':['fft-small','fft-large'],'result_dir':str(session.relative_to(root))}]}
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertFalse(driver.collect_pilot(out,manifest))
            saved = json.loads((out/'pilot.json').read_text())
            self.assertEqual(saved['status'],'coverage_incomplete')
            self.assertEqual(saved['completed_phase_rows'],1)
            self.assertEqual(saved['runs'][0]['missing_workloads'],['fft-large'])


if __name__ == '__main__':
    unittest.main()
