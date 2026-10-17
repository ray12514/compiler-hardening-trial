"""Pinned source/offline builds, fixed caller identity and native MPI metrics."""

import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO/'production'),str(REPO/'scripts')]
import osu
from test_production import inventory


def output(name, value=2, validate=False, size=1024):
    unit = 'Bandwidth (MB/s)' if name=='osu_bw' else 'Avg Latency(us)'
    datatype = 'MPI_INT' if name=='osu_allreduce' else 'MPI_CHAR'
    return f'# OSU MPI Test v7.5.2\n# Datatype: {datatype}.\n# Size {unit}'+(' Validation' if validate else '')+f'\n{size} {value}'+(' Pass' if validate else '')+'\n'


class SourceBuildTests(unittest.TestCase):
    def test_offline_import_verifies_checksum_and_check_never_downloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'trial'; root.mkdir(); incoming=Path(tmp)/'incoming'; incoming.mkdir()
            data=b'pinned source fixture'; (incoming/osu.ARCHIVE).write_bytes(data)
            with patch.object(osu,'SHA256',hashlib.sha256(data).hexdigest()), \
                 patch.object(osu.urllib.request,'urlopen') as network:
                path=osu.prepare(root,argparse.Namespace(check=False,from_dir=incoming))
                self.assertEqual(path.read_bytes(),data)
                self.assertEqual(osu.prepare(root,argparse.Namespace(check=True)),path)
                network.assert_not_called()
            with self.assertRaisesRegex(RuntimeError,'incorrect OSU archive'):
                osu.source(root)

    def test_bad_import_does_not_install_or_leave_partial_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/osu.ARCHIVE).write_bytes(b'wrong')
            with self.assertRaisesRegex(RuntimeError,'checksum mismatch'):
                osu.prepare(root,argparse.Namespace(check=False,from_dir=root))
            self.assertFalse(list((root/'downloads').iterdir()))

    def test_build_uses_reference_flags_and_only_four_targets_without_network_or_mpi_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'runner').mkdir()
            flags={'EXE_CFLAGS':'-O3 -fno-stack-protector','EXE_CXXFLAGS':'-O3','EXE_LDFLAGS':'-no-pie'}
            driver=types.SimpleNamespace(ROOT=root,HERE=root/'runner',require_setup=lambda **kw:None,
                verify_test_tree=lambda *a:None,verify_state=lambda name:{'identity':name},get_flags=lambda arm:flags)
            commands=[]
            def extract(archive,folder):
                path=folder/('osu-micro-benchmarks-'+osu.VERSION); path.mkdir(); (path/'configure').write_text('source')
            def run(command,env,*rest):
                commands.append(command)
                self.assertEqual(env['CC'],'/reference/bin/mpicc')
                self.assertEqual(env['CFLAGS'],flags['EXE_CFLAGS'])
                self.assertNotIn('--disable-papi',command)
                if command[0]=='make':
                    work=Path(command[2])
                    for name in command[6:]:
                        if name in osu.TARGETS:
                            work.mkdir(parents=True,exist_ok=True); (work/name).write_bytes(name.encode())
            with patch.object(osu,'source',return_value=root/'archive'),patch.object(osu,'extract',side_effect=extract), \
                 patch.object(osu.shared,'runtime',return_value={'MPI_PREFIX':'/reference'}), \
                 patch.object(osu.shared,'run',side_effect=run), \
                 patch.object(osu.subprocess,'check_output',return_value='ELF evidence'), \
                 patch.object(osu.urllib.request,'urlopen') as network:
                value=osu.build(driver,argparse.Namespace(retry=False,jobs=2,build_minutes=10))
            self.assertEqual(set(value['binaries']),set(osu.TARGETS))
            self.assertEqual(sum(c[0]=='make' for c in commands),2)
            self.assertFalse(any('mpirun' in c[0] for c in commands)); network.assert_not_called()
            self.assertEqual(osu.verify_build(driver),value)
            Path(value['binaries']['osu_latency']['path']).write_bytes(b'changed')
            with self.assertRaisesRegex(RuntimeError,'executable changed'):
                osu.verify_build(driver)

    def test_installed_osu_commands_are_available_without_rebuilding_packages(self):
        spec=importlib.util.spec_from_file_location('installer',REPO/'scripts/install_driver.py')
        installer=importlib.util.module_from_spec(spec); spec.loader.exec_module(installer)
        with tempfile.TemporaryDirectory() as tmp:
            installer.install(Path(tmp),REPO)
            for action in ('prepare','build','test','report'):
                result=subprocess.run([str(Path(tmp)/'runner/trial'),'osu',action,'--help'],capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stderr)


class NativeMetricTests(unittest.TestCase):
    def test_native_rows_and_validation_require_expected_version_units_size_and_type(self):
        for name in osu.TARGETS:
            self.assertEqual(osu.parse_output(output(name),name,1024),(2.,'MB/s' if name=='osu_bw' else 'us'))
            self.assertEqual(osu.parse_output(output(name,validate=True),name,1024,True)[0],2)
        bad=[output('osu_bw').replace('MB/s','Gb/s'),output('osu_bw')+'1024 3\n',
             output('osu_bw').replace('7.5.2','8.0'),output('osu_bw',value='nan'),output('osu_bw',value=0),
             output('osu_bw').replace('MPI_CHAR','MPI_INT')]
        for text in bad:
            with self.subTest(text=text),self.assertRaises(RuntimeError):
                osu.parse_output(text,'osu_bw',1024)
        with self.assertRaisesRegex(RuntimeError,'validation'):
            osu.parse_output(output('osu_latency',validate=True).replace('Pass','Fail'),'osu_latency',1024,True)

    def test_bandwidth_loss_sign_and_intervals_differ_from_latency_increase(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); cases=[]
            for name in ('osu_bw','osu_latency'):
                cases.append({'name':name,'benchmark':name,'bytes':1024,'unit':'MB/s' if name=='osu_bw' else 'us',
                    'nodes':2,'ranks_per_node':1,'status':'passed','pairs':[
                        {'pair':i,'status':'passed','results':{arm:{'value':v,'process_elapsed_seconds':2}
                            for arm,v in (('full',90),('reference',100))}} for i in range(4)]})
            osu.shared.save(root/'manifest.json',{'status':'finished','requested_pairs':4,'seed':17,'conditions':cases})
            with contextlib.redirect_stdout(io.StringIO()): rows=osu.report(root)
            self.assertAlmostEqual(rows[0]['deterioration_percent'],10)
            self.assertAlmostEqual(rows[1]['deterioration_percent'],-10)
            self.assertAlmostEqual(rows[0]['interval_low_percent'],10)
            self.assertIn('MB/s',(root/'report.html').read_text())
            self.assertNotIn('runtime_increase',(root/'summary.csv').read_text())

    def test_production_gate_rejects_unfinished_or_different_stack(self):
        stacks={arm:{p:{'identity':arm+p} for p in ('openmpi','ucx')} for arm in ('full','reference')}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); value={'status':'finished','scope':'deployment','library_stacks':stacks}
            osu.shared.save(root/'manifest.json',value)
            self.assertEqual(osu.prior_production(root,stacks)['status'],'finished')
            for changed in (dict(value,status='budget_exhausted_partial'),dict(value,scope='stack'),dict(value,library_stacks={})):
                osu.shared.save(root/'manifest.json',changed)
                with self.assertRaises(RuntimeError): osu.prior_production(root,stacks)


class CampaignTests(unittest.TestCase):
    def run_campaign(self, root, interrupt=False):
        runner=root/'runner'; runner.mkdir(); (runner/'procedure.txt').write_text('test')
        driver=types.SimpleNamespace(ROOT=root,HERE=runner,require_setup=lambda **kw:None,
            verify_test_tree=lambda *a:None,verify_state=lambda name:{'identity':name})
        binaries={name:{'path':'/fixed/'+name,'sha256':'same'} for name in osu.TARGETS}
        args=argparse.Namespace(after_production=root/'production',hosts=None,nodes=[2],ranks_per_node=['16','all'],
            benchmarks=['osu_latency','osu_alltoall'],messages=[1024],pairs=4,iterations=20,warmups=5,
            budget_minutes=10,timeout=30,memory_fraction=.25,slurm_overlap=True,seed=17,
            reserved_cpus=None,reservations=None)
        observed=[]
        def launch(env,binary,layout_path,arguments,folder,*a,**kw):
            folder.mkdir(parents=True,exist_ok=True)
            layout=json.loads(layout_path.read_text()); name=Path(binary).name
            self.assertEqual(kw['payload'],'osu')
            if name=='osu_latency': self.assertEqual((len(layout['hosts']),layout['ranks_per_node']),(2,1))
            validation='--validation' in arguments
            observed.append((env['arm'],binary,arguments,folder.name))
            if interrupt and not validation and env['arm']=='reference':
                raise osu.shared.BudgetExhausted('budget exhausted')
            return {'process_elapsed_seconds':.1},output(name,1 if env['arm']=='reference' else 1.1,validation)
        with patch.dict(os.environ,{'SLURM_JOB_ID':'123'}), \
             patch.object(osu,'verify_build',return_value={'binaries':binaries}), \
             patch.object(osu,'prior_production',return_value={'status':'finished'}), \
             patch.object(osu.shared,'allocation',return_value=(['a','b'],{'a':92,'b':92},184,'private job')), \
             patch.object(osu.subprocess,'check_output',return_value='06:00:00'), \
             patch.object(osu.shared,'audit',return_value={'a':inventory(),'b':inventory('b')}), \
             patch.object(osu.shared,'runtime',side_effect=lambda root,arm,overlap:{'arm':arm}), \
             patch.object(osu.shared,'launch_process',side_effect=launch),contextlib.redirect_stdout(io.StringIO()):
            out=osu.test(driver,args)
        return out,observed

    def test_balanced_process_pairs_keep_fixed_binaries_and_point_to_point_uses_two_ranks(self):
        with tempfile.TemporaryDirectory() as tmp:
            out,observed=self.run_campaign(Path(tmp))
            manifest=json.loads((out/'manifest.json').read_text())
            self.assertEqual(manifest['status'],'finished')
            self.assertEqual(len(manifest['conditions']),3)
            self.assertEqual([c['ranks_per_node'] for c in manifest['conditions']],[1,16,92])
            for case in manifest['conditions']:
                self.assertEqual(len(case['pairs']),4)
                self.assertEqual(sum(o[0]=='full' for o in case['planned_order']),2)
                self.assertTrue(all(p['status']=='passed' for p in case['pairs']))
            self.assertEqual(len({binary for _,binary,_,_ in observed}),2)
            self.assertEqual(len(json.loads((out/'summary.json').read_text())['summaries']),3)
            self.assertNotIn('private job',(out/'report.html').read_text())

    def test_budget_partial_retains_pair_but_does_not_compute_an_unpaired_estimate(self):
        with tempfile.TemporaryDirectory() as tmp:
            out,_=self.run_campaign(Path(tmp),interrupt=True)
            manifest=json.loads((out/'manifest.json').read_text())
            self.assertEqual(manifest['status'],'budget_exhausted_partial')
            self.assertEqual(manifest['conditions'][0]['status'],'budget_exhausted_partial')
            self.assertEqual(json.loads((out/'summary.json').read_text())['summaries'],[])
            self.assertEqual(manifest['conditions'][1]['status'],'pending')


if __name__=='__main__':
    unittest.main()
