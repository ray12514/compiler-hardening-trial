"""CPU reservation safety, bounded orchestration and paired export regressions."""

import argparse
import contextlib
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
sys.path.insert(0,str(REPO/'production'))
sys.path.insert(0,str(REPO/'scripts'))
import campaign
import placement
import rank as production_rank


def inventory(host='a', allowed=None, smt=False):
    count = 192 if smt else 96
    return {'host':host,'job_id':'123','online':list(range(count)),
        'allowed':list(range(count)) if allowed is None else allowed,
        'reserved':[19,20,21,22], 'reservation_evidence':[],
        'job_cpuset_file':'/private/job_123/cpuset.cpus.effective',
        'available_memory_bytes':1024**4,
        'topology':{str(i):{'socket':i%96//48,'core':i%48,'numa':i%96//24,
            'siblings':[i%96,i%96+96] if smt else [i]} for i in range(count)}}


def args(**overrides):
    values = dict(nodes=[2],ranks_per_node=['16'],workloads=list(campaign.MODES),shape=None,
        fft_mib_per_rank=8,io_mib_per_rank=8,checkpoint_every=4,pairs=4,target_seconds=1,
        max_steps=8,budget_minutes=10,timeout=10,memory_fraction=.25,max_checkpoint_gib=8,
        max_written_gib=1024,seed=16,slurm_overlap=True,reserved_cpus=None,reservations=None,
        audit_only=False,report=None,hosts=None,groups_per_scale=1)
    return argparse.Namespace(**(values|overrides))


class PlacementTests(unittest.TestCase):
    def test_no_job_cgroup_uses_explicit_full_capacity_slurm_task_binding(self):
        with patch.dict(os.environ,{'SLURM_JOB_ID':'123','SLURM_STEP_ID':'7',
                 'SLURM_LOCALID':'0','SLURM_CPUS_PER_TASK':'92','SLURM_CPU_BIND_TYPE':'threads',
                 'TRIAL_PRODUCTION_ALLOCATION_CPUS':'92','TRIAL_PRODUCTION_TASK_PLUGIN':'task/affinity'},clear=True), \
             patch.object(placement,'job_cgroup',side_effect=RuntimeError('Cannot locate this Slurm job cgroup. No CPU grant inferred from the shell.')), \
             patch.object(placement,'topology',return_value=(set(range(96)),inventory()['topology'])), \
             patch.object(placement,'memory_available',return_value=1024**4), \
             patch.object(placement.Path,'read_text',return_value='model name : test'), \
             patch.object(placement.os,'sched_getaffinity',return_value=set(range(92)),create=True):
            grant=placement.inventory(reserved='19-22')
        self.assertEqual(set(grant['allowed']),set(range(92)))
        self.assertEqual(grant['allocation_source'],'slurm-full-capacity-task-binding')

    def test_no_cgroup_never_uses_a_shell_or_undersized_task_affinity(self):
        with patch.object(placement,'job_cgroup',side_effect=RuntimeError('Cannot locate this Slurm job cgroup')), \
             patch.object(placement.os,'sched_getaffinity',return_value={0},create=True), \
             patch.dict(os.environ,{'SLURM_JOB_ID':'123','SLURM_CPUS_PER_TASK':'92',
                 'SLURM_LOCALID':'0','SLURM_STEP_ID':'7'},clear=True):
            with self.assertRaisesRegex(RuntimeError,'full-capacity'):
                placement.allocation_grant(92)
            with self.assertRaisesRegex(RuntimeError,'Cannot locate'):
                placement.allocation_grant()

    def test_fallback_rejects_ignored_binding_or_interactive_shell(self):
        base={'SLURM_JOB_ID':'123','SLURM_CPUS_PER_TASK':'92','SLURM_LOCALID':'0',
              'SLURM_STEP_ID':'7','SLURM_CPU_BIND_TYPE':'mask_cpu:',
              'TRIAL_PRODUCTION_TASK_PLUGIN':'task/affinity'}
        for extra,mask in (({},set(range(96))),({'SLURM_STEP_ID':'interactive'},set(range(92))),
                           ({'TRIAL_PRODUCTION_TASK_PLUGIN':'task/none'},set(range(92))),
                           ({'SLURM_CPU_BIND_TYPE':'none'},set(range(92)))):
            with self.subTest(extra=extra,mask_size=len(mask)), patch.dict(os.environ,base|extra,clear=True), \
                 patch.object(placement,'job_cgroup',side_effect=RuntimeError('Cannot locate this Slurm job cgroup')), \
                 patch.object(placement.os,'sched_getaffinity',return_value=mask,create=True), \
                 self.assertRaisesRegex(RuntimeError,'full-capacity'):
                placement.allocation_grant(92)

    def test_92_slot_job_with_full_mask_can_use_92_safe_cores(self):
        info = {'a':inventory(),'b':inventory('b')}
        layout = placement.make_layout(info,['a','b'],'all',{'a':92,'b':92},184)
        self.assertEqual(layout['ranks_per_node'],92)
        self.assertFalse(set(layout['hosts']['a']['cpus']) & {19,20,21,22})

    def test_92_cpu_mask_including_weka_cannot_reclaim_unallocated_cores(self):
        info = {'a':inventory(allowed=list(range(92))),'b':inventory('b')}
        layout = placement.make_layout(info,['a','b'],'all',{'a':92,'b':92},184)
        self.assertEqual(layout['ranks_per_node'],88)
        self.assertLess(max(layout['hosts']['a']['cpus']),92)
        with self.assertRaisesRegex(RuntimeError,'only 88'):
            placement.make_layout(info,['a','b'],'92',{'a':92,'b':92},184)

    def test_smt_siblings_and_nonidentical_node_reservations_are_excluded(self):
        a,b = inventory(smt=True),inventory('b',smt=True)
        b['reserved']=[0,1,2,3,4,5]
        layout = placement.make_layout({'a':a,'b':b},['a','b'],'all',{'a':192,'b':192},384)
        self.assertEqual(layout['ranks_per_node'],90)
        for host,info in (('a',a),('b',b)):
            row=layout['hosts'][host]
            self.assertFalse(set(row['cpus']) & set(row['excluded_cpus']))
            physical={(info['topology'][str(cpu)]['socket'],info['topology'][str(cpu)]['core']) for cpu in row['cpus']}
            self.assertEqual(len(physical),90)

    def test_16_core_prefix_spans_numa_and_job_task_limit_is_separate(self):
        info=inventory()
        cpus,_=placement.eligible(info)
        self.assertEqual({info['topology'][str(cpu)]['numa'] for cpu in cpus[:16]},set(range(4)))
        with self.assertRaisesRegex(RuntimeError,'task capacity'):
            placement.make_layout({'a':info},['a'],'16',{'a':92},8)

    def test_cgroup_v2_inherited_mask_uses_effective_job_ancestor(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); proc=root/'proc'; (proc/'self').mkdir(parents=True)
            (proc/'self/cgroup').write_text('0::/slurm/uid_1/job_123/step_0/task_0\n')
            job=root/'cgroup/slurm/uid_1/job_123'; job.mkdir(parents=True)
            (job/'cpuset.cpus').write_text('')
            (job/'cpuset.cpus.effective').write_text('0-95')
            directory,mask,_=placement.job_cgroup('123',proc,root/'cgroup')
            self.assertEqual(directory,job)
            self.assertEqual(len(mask),96)

    def test_cgroup_v1_and_missing_job_do_not_use_shell_affinity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); proc=root/'proc'; (proc/'self').mkdir(parents=True)
            (proc/'self/cgroup').write_text('3:cpuset:/slurm/uid_1/job_123/step_0\n')
            job=root/'cgroup/cpuset/slurm/uid_1/job_123'; job.mkdir(parents=True)
            (job/'cpuset.effective_cpus').write_text('4-95')
            self.assertEqual(len(placement.job_cgroup('123',proc,root/'cgroup')[1]),92)
            with self.assertRaisesRegex(RuntimeError,'Cannot locate'):
                placement.job_cgroup('456',proc,root/'cgroup')

    def test_cgroup_mount_root_is_resolved_from_mountinfo(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); proc=root/'proc'; (proc/'self').mkdir(parents=True)
            (proc/'self/cgroup').write_text('0::/slurm/uid_1/job_123/step_0\n')
            point=root/'mounted'; job=point/'uid_1/job_123'; job.mkdir(parents=True)
            (proc/'self/mountinfo').write_text(f'1 0 0:1 /slurm {point} rw - cgroup2 cgroup rw\n')
            (job/'cpuset.cpus.effective').write_text('4-95')
            self.assertEqual(placement.job_cgroup('123',proc)[0],job)

    def test_ambiguous_weka_mask_stops_instead_of_guessing_19_22(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); service=root/'weka.slice'; service.mkdir()
            path=service/'cpuset.cpus.effective'; path.write_text('0-95')
            with self.assertRaisesRegex(RuntimeError,'No unambiguous WEKA'):
                placement.weka_masks(set(range(96)),root)
            path.write_text('19-22')
            self.assertEqual(placement.weka_masks(set(range(96)),root)[0],{19,20,21,22})
            path.unlink()
            (service/'cpuset.cpus').write_text('19-22')
            self.assertEqual(placement.weka_masks(set(range(96)),root)[0],{19,20,21,22})

    def test_resource_parser_reads_core_ids_without_network_or_management_fields(self):
        text='ROLES       NODE ID  CORE ID\nMANAGEMENT  0        <auto>\nFRONTEND    1        19\nFRONTEND    2        20\n\nNET DEVICE IDENTIFIER\nFRONTEND 123 999\n'
        self.assertEqual(placement.resource_cpus(text),{19,20})
        self.assertEqual(placement.resource_cpus('unknown output 19 20'),set())

    def test_weka_only_lookup_does_not_require_a_slurm_cgroup(self):
        output=io.StringIO()
        with patch.object(sys,'argv',['placement.py','--show-weka']), \
             patch.object(placement,'topology',return_value=(set(range(96)),{})), \
             patch.object(placement,'weka_resources',return_value={21}), \
             patch.object(placement,'weka_masks',return_value=({19,20},[])), \
             patch.object(placement,'job_cgroup') as job, contextlib.redirect_stdout(output):
            placement.main()
        job.assert_not_called()
        self.assertEqual(json.loads(output.getvalue()),{'weka_os_cpus':[19,20,21]})


class CampaignTests(unittest.TestCase):
    def test_audit_requests_full_capacity_and_reaches_inventory_without_cgroups(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp); seen=[]
            def run(command,env,folder,timeout,deadline):
                self.assertIn('--cpus-per-task=96',command)
                self.assertIn('--cpu-bind=verbose,threads',command)
                self.assertIn('--overlap',command)
                self.assertNotIn('SLURM_CPU_BIND_LIST',env)
                self.assertNotIn('SLURM_TRES_PER_TASK',env)
                host=next(v.split('=',1)[1] for v in command if v.startswith('--nodelist='))
                child=env|{'SLURM_STEP_ID':'7','SLURM_LOCALID':'0','SLURM_CPUS_PER_TASK':'96',
                           'SLURM_CPU_BIND_TYPE':'mask_cpu:'}
                with patch.dict(os.environ,child,clear=True), \
                     patch.object(placement,'job_cgroup',side_effect=RuntimeError('Cannot locate this Slurm job cgroup')), \
                     patch.object(placement,'topology',return_value=(set(range(96)),inventory()['topology'])), \
                     patch.object(placement,'memory_available',return_value=1024**4), \
                     patch.object(placement.Path,'read_text',return_value='model name : test'), \
                     patch.object(placement.os,'sched_getaffinity',return_value=set(range(96)),create=True), \
                     patch.object(placement.socket,'gethostname',return_value=host):
                    value=placement.inventory('19-22')
                (out/'inventory'/f'{host}.json').write_text(json.dumps(value))
                seen.append(host)
            with patch.dict(os.environ,{'SLURM_JOB_ID':'123','SLURM_CPU_BIND_LIST':'old',
                    'SLURM_TRES_PER_TASK':'cpu=1','SLURM_JOB_CPUS_PER_NODE':'96(x2)'}), \
                 patch.object(campaign.subprocess,'check_output',return_value='TaskPlugin = task/affinity\n'), \
                 patch.object(campaign,'run',side_effect=run):
                values=campaign.audit(args(reserved_cpus='19-22'),out,['a','b'],100,{'a':92,'b':92})
            self.assertEqual(seen,['a','b'])
            layout=placement.make_layout(values,['a','b'],'all',{'a':92,'b':92},184)
            self.assertEqual(layout['ranks_per_node'],92)
            self.assertEqual(layout['hosts']['a']['allocation_source'],'slurm-full-capacity-task-binding')
    def test_host_groups_are_bounded_and_do_not_repeat_full_allocation(self):
        hosts=list('abcdefgh')
        self.assertEqual(campaign.host_groups(hosts,2,2),[['a','b'],['c','d']])
        self.assertEqual(campaign.host_groups(hosts,4,10),[list('abcd'),list('efgh')])
        self.assertEqual(campaign.host_groups(hosts,8,10),[hosts])
    def test_balanced_shape_supports_more_ranks_than_old_caller_limit(self):
        for ranks in (1,32,184,368,736):
            nx,ny,nz=campaign.shape_for(ranks,8)
            self.assertEqual(nx%ranks,0)
            self.assertEqual(ny*nz%ranks,0)
            self.assertGreaterEqual(nx,ranks)
            self.assertGreaterEqual(nx*ny*nz*16/ranks,8*1024**2)

    def test_slot_counts_and_job_task_limit_are_parsed_separately(self):
        with patch.dict(os.environ,{'SLURM_JOB_ID':'123','SLURM_JOB_NODELIST':'a,b','SLURM_JOB_CPUS_PER_NODE':'96(x2)'}), \
             patch.object(campaign.subprocess,'check_output',side_effect=['a\nb\n','NumTasks=184 NtasksPerN:B:S:C=92:0:*:*']):
            hosts,counts,tasks,_=campaign.allocation()
        self.assertEqual((hosts,counts,tasks),(['a','b'],{'a':92,'b':92},184))

    def test_timed_run_cleans_up_its_process_group_and_preserves_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'failed'
            with self.assertRaises(subprocess.TimeoutExpired):
                campaign.run(['bash','-c','echo started; sleep 60'],os.environ.copy(),folder,1,
                             campaign.time.monotonic()+10)
            self.assertIn('started',(folder/'command.log').read_text())
            self.assertEqual(json.loads((folder/'command.json').read_text())['status'],'failed_or_interrupted')

    def test_runtime_preserves_private_paths_rdma_and_interactive_overlap(self):
        env={'MPI_PREFIX':'/private/mpi','UCX_PREFIX':'/private/ucx','UCX_TLS':'rc,sm,self',
             'OMPI_MCA_plm_slurm_args':'--kill-on-bad-exit=1','UCX_LOG_LEVEL':'info'}
        with patch.object(campaign,'activated_env',return_value=(env.copy(),'saved')):
            result=campaign.runtime(Path('/private/trial'),'reference',True)
        self.assertNotIn('UCX_PREFIX',result)
        self.assertNotIn('UCX_LOG_LEVEL',result)
        self.assertEqual(result['TRIAL_UCX_PREFIX'],'/private/ucx')
        self.assertEqual(result['OMPI_MCA_plm_slurm_args'],'--kill-on-bad-exit=1 --overlap')
        self.assertEqual(result['OMP_NUM_THREADS'],'1')
        for tls in ('all','tcp,sm,self','rc,tcp,sm,self'):
            with patch.object(campaign,'activated_env',return_value=({**env,'UCX_TLS':tls},'saved')), \
                 self.assertRaisesRegex(RuntimeError,'no TCP'):
                campaign.runtime(Path('/trial'),'full',False)

    def test_campaign_freezes_equal_work_balances_order_and_exports_completed_pairs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); runner=root/'runner'; runner.mkdir(); (runner/'procedure.txt').write_text('test-commit')
            driver=types.SimpleNamespace(ROOT=root,HERE=runner,require_setup=lambda **kw:None,
                verify_test_tree=lambda *a:None, read=lambda *a:{'identity':'complete-test'})
            observed=[]
            def launch(env,binary,layout_path,arguments,folder,*rest,**kwargs):
                layout=json.loads(layout_path.read_text())
                if arguments==['qualify']: return {'qualification_passed':True}
                mode=arguments[0]; steps=int(arguments[4])
                if arguments[-1]==1:
                    return {'preflight_passed':True,'estimated_rank_bytes':4096,'local_slabs_min':1,
                            'local_slabs_max':1,'checkpoint_bytes':0 if mode=='fft' else 1024}
                observed.append((env['arm'],str(layout_path),tuple(arguments[:7]),folder.name))
                return {'loop_seconds':.05*steps*(1.1 if env['arm']=='full' else 1),
                    'process_elapsed_seconds':.1+.05*steps,'planning_seconds':.01,'steps':steps,
                    'checkpoints':0 if mode=='fft' else steps,'checkpoint_bytes':0 if mode=='fft' else 1024,
                    'max_rank_rss_bytes':1024,'error':1e-12,'iterations':[{'step':1,
                    'compute_maxrank_seconds':.05,'write_maxrank_seconds':0}], 'io_modes':[]}
            with patch.dict(os.environ,{'SLURM_JOB_ID':'123','IO_DIR':str(root/'io')}), \
                 patch.object(campaign,'allocation',return_value=(['a','b'],{'a':92,'b':92},184,'private')), \
                 patch.object(campaign.subprocess,'check_output',return_value='06:00:00'), \
                 patch.object(campaign,'audit',return_value={'a':inventory(),'b':inventory('b')}), \
                 patch.object(campaign,'runtime',side_effect=lambda root,arm,overlap:{'arm':arm}), \
                 patch.object(campaign,'compile_callers',return_value={arm:{'binary':'/test/'+arm} for arm in ('full','reference')}), \
                 patch.object(campaign,'launch',side_effect=launch), contextlib.redirect_stdout(io.StringIO()):
                out=campaign.campaign(driver,args(max_written_gib=100*1024/1024**3))
            manifest=json.loads((out/'manifest.json').read_text())
            self.assertEqual(manifest['status'],'finished')
            self.assertLessEqual(manifest['logical_write_bytes_reserved'],100*1024)
            self.assertTrue(any('io_budget_step_cap' in c for c in manifest['conditions']))
            for condition in manifest['conditions']:
                self.assertEqual(condition['status'],'passed')
                self.assertEqual(len(condition['pairs']),4)
                self.assertEqual(sum(order[0]=='full' for order in condition['planned_order']),2)
                for pair in condition['pairs']:
                    self.assertEqual(pair['status'],'passed')
                    self.assertEqual(pair['results']['full']['steps'],pair['results']['reference']['steps'])
            summaries=json.loads((out/'summary.json').read_text())['summaries']
            self.assertEqual(len(summaries),4)
            self.assertTrue(all(abs(row['runtime_increase_percent']-10)<1e-8 for row in summaries))
            for name in ('pairs.csv','iterations.csv','io-modes.csv','summary.csv','report.html'):
                self.assertTrue((out/name).is_file())
            self.assertNotIn('private',(out/'report.html').read_text())
            for a,b in zip(observed[2::2],observed[3::2]):
                # Pair launch placement/work must not depend on the arm.
                self.assertEqual(a[1:3],b[1:3])

    def test_failed_and_unpaired_results_are_retained_but_not_in_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            value={'loop_seconds':1,'process_elapsed_seconds':2,'planning_seconds':.1,'checkpoints':1,
                   'checkpoint_bytes':8,'max_rank_rss_bytes':1024,'error':0,'iterations':[],'io_modes':[]}
            manifest={'status':'failed_or_interrupted','seed':1,'requested_pairs':10,'conditions':[
                {'name':'2nodes-16rpn-fft','nodes':2,'ranks_per_node':16,'steps':1,'status':'measuring',
                 'pairs':[{'pair':0,'status':'running','results':{'full':value}}]}]}
            campaign.save(out/'manifest.json',manifest)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(campaign.report(out),[])
            self.assertIn('False',(out/'pairs.csv').read_text())

    def test_installer_copies_production_sources_and_installed_help_works(self):
        spec=importlib.util.spec_from_file_location('installer',REPO/'scripts/install_driver.py')
        installer=importlib.util.module_from_spec(spec); spec.loader.exec_module(installer)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); installer.install(root,REPO)
            result=subprocess.run([str(root/'runner/trial'),'production','--help'],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('--audit-only',result.stdout)
            self.assertTrue((root/'runner/production/workload.c').is_file())


class RankGuardTests(unittest.TestCase):
    def test_missing_cgroup_uses_audited_binding_only_for_same_job(self):
        row={'allocation_source':'slurm-full-capacity-task-binding','allowed_cpus':[7,9],
             'binding_proof':{'step_id':'7','cpus_per_task':2,'task_plugin':'task/affinity','binding_type':'mask_cpu'}}
        with patch.dict(os.environ,{'SLURM_JOB_ID':'123'}), \
             patch.object(production_rank,'job_cgroup',side_effect=RuntimeError('Cannot locate this Slurm job cgroup')):
            self.assertEqual(production_rank.allowed_cpus({'job_id':'123'},row),{7,9})
            with self.assertRaisesRegex(RuntimeError,'Cannot locate'):
                production_rank.allowed_cpus({'job_id':'another-job'},row)
            with self.assertRaisesRegex(RuntimeError,'Cannot locate'):
                production_rank.allowed_cpus({'job_id':'123'},dict(row,binding_proof={}))
    def test_guard_applies_exact_os_cpu_and_keeps_threads_on_one_core(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); layout=root/'layout.json'
            layout.write_text(json.dumps({'ranks_per_node':1,'hosts':{'a':{'cpus':[7],
                'excluded_cpus':[19,20,21,22],'reservation_evidence':[],
                'memory_budget_bytes':1024**3}}}))
            env={'OMPI_COMM_WORLD_RANK':'0','OMPI_COMM_WORLD_LOCAL_RANK':'0',
                'OMPI_COMM_WORLD_LOCAL_SIZE':'1','SLURM_JOB_ID':'123','TRIAL_MPI_PREFIX':'/mpi',
                'TRIAL_UCX_PREFIX':'/ucx','TRIAL_ROOT':str(root),'TRIAL_PRODUCTION_ARM':'full',
                'OMP_NUM_THREADS':'92'}
            loaded='libmpi.so => /mpi/lib/libmpi.so\n'
            loaded+=f'libfftw3.so => {root}/install/fftw-mpi/full/lib/libfftw3.so\n'
            loaded+=f'libhdf5.so => {root}/install/hdf5-mpi/full/lib/libhdf5.so\n'
            with patch.object(sys,'argv',['rank.py',str(layout),str(root),'/loop','qualify']), \
                 patch.dict(os.environ,env,clear=True), patch.object(production_rank.socket,'gethostname',return_value='a'), \
                 patch.object(production_rank,'job_cgroup',return_value=(root,{7,19},root)), \
                 patch.object(production_rank.os,'sched_setaffinity',create=True) as pin, \
                 patch.object(production_rank.os,'sched_getaffinity',return_value={7},create=True), \
                 patch.object(production_rank.subprocess,'check_output',side_effect=[loaded,'libucp.so => /ucx/lib/libucp.so']), \
                 patch.object(production_rank.os,'execve') as execute, contextlib.redirect_stderr(io.StringIO()):
                production_rank.main()
            pin.assert_called_once_with(0,{7})
            self.assertEqual(execute.call_args.args[2]['OMP_NUM_THREADS'],'1')
            self.assertEqual(json.loads((root/'rank-0.json').read_text())['cpus'],[7])

    def test_guard_rejects_mixed_libraries(self):
        with self.assertRaisesRegex(RuntimeError,'Missing/mixed'):
            production_rank.libraries('libmpi.so => /system/lib/libmpi.so',r'libmpi',Path('/private/mpi'))


if __name__=='__main__':
    unittest.main()
