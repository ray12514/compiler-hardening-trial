import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('maintenance_stage',Path(__file__).with_name('patch_miniforge_trust.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class StageTests(unittest.TestCase):
 def test_cli_stage_is_explicit_and_bypasses_shared_group_and_write_checks(self):
  with patch.object(m.sys,'argv',['script','/base','--stage','/private/candidate']),patch.object(m,'find_base',return_value=Path('/base')),patch.object(m,'stage_base',return_value=0) as stage,patch.object(m,'maintenance_gid') as group,patch.object(m,'maintainable') as write:
   self.assertEqual(m.main(),0)
  group.assert_not_called();write.assert_not_called()
  self.assertEqual(stage.call_args.args[2]['PYTHONDONTWRITEBYTECODE'],'1')

 def test_stage_rejects_live_apply_and_unrelated_modes_before_any_access(self):
  for extra in (['--apply'],['--all-envs'],['--only','/env'],['--report','latest'],['--log-dir','/logs'],['--trust-only'],['--diagnostic-timeout','1']):
   with self.subTest(extra=extra),patch.object(m.sys,'argv',['script','--stage','/private/candidate']+extra),patch.object(m,'find_base') as find,patch('sys.stderr',io.StringIO()):
    with self.assertRaises(SystemExit):m.main()
    find.assert_not_called()

 def test_skip_requires_stage_and_plain_names(self):
  for args in (['--stage-skip','qt6-main'],['--stage','/new','--stage-skip','qt6-main<6.9']):
   with self.subTest(args=args),patch.object(m.sys,'argv',['script']+args),patch.object(m,'find_base') as find,patch('sys.stderr',io.StringIO()):
    with self.assertRaises(SystemExit):m.main()
    find.assert_not_called()

 def test_stage_destination_cannot_reuse_or_nest_in_live_prefix(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);base=root/'base';(base/'conda-meta').mkdir(parents=True);(base/'conda-meta/history').touch()
   for destination in (base/'candidate',root,base):
    with self.subTest(destination=destination),self.assertRaises(RuntimeError):
     m.stage_base(SimpleNamespace(stage=destination),base,{})
   marker=root/'existing';marker.mkdir();(marker/'keep').write_text('existing candidate')
   with self.assertRaisesRegex(RuntimeError,'must be new'):m.stage_base(SimpleNamespace(stage=marker),base,{})
   self.assertEqual((marker/'keep').read_text(),'existing candidate')
   dangling=root/'dangling';dangling.symlink_to(root/'not-created')
   with self.assertRaisesRegex(RuntimeError,'must be new'):m.stage_base(SimpleNamespace(stage=dangling),base,{})
   self.assertFalse((root/'not-created').exists())

 def test_omission_changes_requests_without_claiming_dependencies_are_unavailable(self):
  meta={'app':{},'qt6-main':{},'krb5':{}}
  intent={'roots':['app','qt6-main'],'replacements':[]}
  roots,specs,omitted=m.stage_requests(meta,intent,['qt6-main'],'26.9.4')
  self.assertNotIn('qt6-main',roots);self.assertIn('app',roots);self.assertIn('conda>=26.9.4',specs)
  self.assertEqual(omitted,{'qt6-main'})
  rows=m.stage_comparison({'krb5':{'version':'1.21','build':'old'}},{},['app'],roots,omitted,True)
  self.assertEqual(next(r for r in rows if r['package']=='krb5')['status'],'not-selected')
  self.assertIn('does not establish unavailability',next(r for r in rows if r['package']=='krb5')['note'])
  for name in ('conda','certifi','pip'):
   with self.subTest(name=name),self.assertRaises(RuntimeError):m.stage_requests({name:{}},intent,[name],'26.9.4')
  with self.assertRaisesRegex(RuntimeError,'Unknown'):m.stage_requests(meta,intent,['typo'],'26.9.4')

 def run_stage(self,skip=(),fail=None,change_source=False,offline=False,mirror=False):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);base=root/'base';(base/'bin').mkdir(parents=True);(base/'conda-meta').mkdir()
   (base/'bin/conda').touch();(base/'bin/python').touch();(base/'conda-meta/history').write_text('original history')
   (base/'.condarc').write_text('pinned_packages: [qt6-main==6.8.1]\n')
   source=root/'site.pem';source.write_text('original PEM')
   meta={n:{'name':n,'version':v,'build':'old','channel':'conda-forge','depends':deps} for n,v,deps in (
    ('conda','24.11.2',['python','conda-libmamba-solver']),('python','3.12.8',[]),('conda-libmamba-solver','24.9.0',['python']),
    ('ca-certificates','2024.12.14',[]),('certifi','2024.12.14',['python']),('pip','24.3.1',['python']),
    ('pyside6','6.8.1',['qt6-main','python']),('qt6-main','6.8.1',['krb5']),('krb5','1.21.3',[]))}
   meta['pyside6']['files']=['bin/android_deploy.py']
   (base/'bin/android_deploy.py').write_text('original Qt tool')
   cache=base/'bin/__pycache__/android_deploy.cpython-312.pyc';cache.parent.mkdir();cache.write_bytes(b'original cache');cache.parent.chmod(0o555)
   for name,record in meta.items():(base/'conda-meta'/(name+'.json')).write_text(json.dumps(record))
   original={str(p.relative_to(base)):(p.read_bytes(),p.stat().st_ino,p.stat().st_mode) for p in base.rglob('*') if p.is_file()}
   args=SimpleNamespace(stage=root/'stage',stage_skip=list(skip),offline=offline,channel=[(root/'mirror').as_uri()] if mirror else [],ca_bundle=source,extra_ca=[])
   candidate=args.stage/'env';calls=[]
   versions={'conda':'26.9.4','python':'3.14.0','conda-libmamba-solver':'26.10.0','ca-certificates':'2026.10.23',
             'certifi':'2026.10.23','pip':'26.2.2','pyside6':'6.12.0','qt6-main':'6.12.0','krb5':'1.22.2'}
   chosen={n:dict(meta[n],version=v,build='new') for n,v in versions.items() if not (skip and n in ('pyside6','qt6-main','krb5'))}
   for name in ('curl','libcurl'):chosen[name]={'name':name,'version':'8.23.0','build':'0','channel':'conda-forge'}
   def fake(argv,**kwargs):
    argv=list(map(str,argv));values=argv[5:];calls.append((argv,dict(kwargs['env'])))
    if argv[4]==m.CURL_PROBE:
     if fail=='curl-probe':return subprocess.CompletedProcess(argv,1,'','Missing Conda curl executable')
     data={'version':'8.23.0','loaded_libcurl':'8.23.0'}
    elif argv[4]==m.AUDIT:data={'packages':{},'bundles':{}}
    elif values==['__cse_solver_probe__']:
     if fail=='probe' and argv[0]==str(candidate/'bin/python'):return subprocess.CompletedProcess(argv,1,'','Candidate cannot import solver')
     data={'success':True,'solver':'libmamba'}
    elif '--show' in values:data={'pinned_packages':['qt6-main==6.8.1','python=3.12']}
    elif 'search' in values:data={'conda':[{'version':'26.9.4','channel':'conda-forge'}]}
    elif '--explicit' in values:return subprocess.CompletedProcess(argv,0,'@EXPLICIT\n','')
    elif values and values[0]=='create':
     self.assertEqual(values[values.index('-p')+1],str(candidate))
     if '--dry-run' in values:
      if fail=='timeout':raise subprocess.TimeoutExpired(argv,180,output=b'partial Qt solver output')
      if fail=='solve':return subprocess.CompletedProcess(argv,1,json.dumps({'success':False,'exception_name':'LibMambaUnsatisfiableError','message':'qt6-main requires krb5 <1.22; conflicting app requires krb5 >=1.22'}),'')
      data={'success':True,'actions':{'PREFIX':str(candidate),'LINK':list(chosen.values())}}
     else:
      (candidate/'conda-meta').mkdir(parents=True);(candidate/'bin').mkdir()
      (candidate/'bin/python').touch();(candidate/'bin/conda').touch()
      for name,r in chosen.items():
       if fail=='install' and name!='python':continue
       (candidate/'conda-meta'/(name+'.json')).write_text(json.dumps(r))
      if change_source=='corrupt-metadata':(base/'conda-meta/conda.json').write_text('partial concurrent JSON')
      elif change_source:(base/'.condarc').write_text('concurrent edit')
      if fail=='install':return subprocess.CompletedProcess(argv,1,'','Private package link failed')
      data={'success':True}
    else:data={'success':True}
    return subprocess.CompletedProcess(argv,0,json.dumps(data),'')
   try:
    with patch.object(m.subprocess,'run',side_effect=fake),patch.object(m,'filtered_bundle',return_value=('private PEM',[])),patch.object(m,'maintenance_gid') as group,patch.object(m,'public_permissions') as permissions,contextlib.redirect_stdout(io.StringIO()):
     result=m.stage_base(args,base,m.safe_environment())
    group.assert_not_called();permissions.assert_not_called()
    summary=json.loads((args.stage/'stage-summary.json').read_text());comparison=json.loads((args.stage/'comparison.json').read_text())
    review=(args.stage/'review.md').read_text()
    self.assertEqual(args.stage.stat().st_mode&0o777,0o700)
    self.assertTrue(all(p.stat().st_mode&0o077==0 for p in args.stage.iterdir() if p.is_file()))
    self.assertEqual(cache.read_bytes(),b'original cache');self.assertEqual(cache.parent.stat().st_mode&0o777,0o555)
    if not change_source:self.assertEqual(original,{str(p.relative_to(base)):(p.read_bytes(),p.stat().st_ino,p.stat().st_mode) for p in base.rglob('*') if p.is_file()})
    self.assertEqual(source.read_text(),'original PEM')
    for argv,env in calls:
     self.assertEqual(argv[1:4],['-I','-B','-c']);self.assertNotIn('CSE_CONDA_PERMISSION_HOLDS',env)
     self.assertEqual(env['CONDA_PKGS_DIRS'],str(args.stage/'pkgs'));self.assertEqual(env['CONDA_REGISTER_ENVS'],'false')
    return result,summary,comparison,review,calls
   finally:cache.parent.chmod(0o755)

 def test_fresh_private_candidate_updates_qt_kerberos_without_source_permission_holds(self):
  result,summary,comparison,review,calls=self.run_stage()
  self.assertEqual(result,0,summary['issues']);self.assertEqual(summary['status'],'ready-for-review')
  self.assertTrue(summary['source_metadata_unchanged']);self.assertTrue(summary['source_ca_unchanged'])
  self.assertFalse(summary['promotion_performed']);self.assertEqual([h['name'] for h in summary['source_permission_holds']],['pyside6'])
  creates=[argv[5:] for argv,env in calls if argv[5:6]==['create']]
  self.assertEqual(len(creates),2);self.assertIn('pyside6',creates[0]);self.assertIn('python',creates[0]);self.assertIn('--no-pin',creates[0])
  self.assertNotIn('python=3.12.*',creates[0]);self.assertFalse(any('pyside6=6.8.1' in value for value in creates[0]))
  krb=next(r for r in comparison if r['package']=='krb5');self.assertEqual((krb['before_version'],krb['after_version']),('1.21.3','1.22.2'))
  self.assertIn('No promotion',review)

 def test_explicitly_omitted_request_appears_in_comparison(self):
  result,summary,comparison,review,calls=self.run_stage(skip=['pyside6'])
  self.assertEqual(result,0);self.assertEqual(summary['omitted_requests'],['pyside6'])
  pyside=next(r for r in comparison if r['package']=='pyside6')
  self.assertEqual(pyside['status'],'not-selected');self.assertIn('explicitly omitted',pyside['note'])
  self.assertIn('Explicitly omitted requests: pyside6',review)

 def test_joint_solve_failure_writes_review_and_never_attempts_install(self):
  result,summary,comparison,review,calls=self.run_stage(fail='solve')
  self.assertEqual(result,2);self.assertEqual(summary['status'],'solve-failed')
  self.assertTrue(summary['source_metadata_unchanged']);self.assertIn('krb5',' '.join(summary['issues']))
  self.assertFalse(any('--yes' in argv for argv,env in calls))
  self.assertTrue(all(r['status']=='not-installed' for r in comparison));self.assertIn('individual package availability',comparison[0]['note'])

 def test_planning_timeout_retains_partial_output_and_no_install_claim(self):
  result,summary,comparison,review,calls=self.run_stage(fail='timeout')
  self.assertEqual(result,2);self.assertEqual(summary['status'],'solve-failed')
  self.assertIn('timed out after 180s',' '.join(summary['issues']));self.assertIn('partial Qt',' '.join(summary['issues']))
  self.assertFalse(any('--yes' in argv for argv,env in calls));self.assertIsNone(summary['commands'][-1]['returncode'])

 def test_fresh_offline_stage_requires_and_uses_an_explicit_file_mirror(self):
  result,summary,comparison,review,calls=self.run_stage(offline=True)
  self.assertEqual(result,2);self.assertIn('fresh offline stage needs',' '.join(summary['issues']))
  self.assertFalse(any(argv[5:6]==['create'] for argv,env in calls))
  result,summary,comparison,review,calls=self.run_stage(offline=True,mirror=True)
  self.assertEqual(result,0,summary['issues'])
  search=next(argv for argv,env in calls if argv[5:6]==['search'])
  self.assertTrue(search[search.index('--channel')+1].startswith('file://'))
  self.assertTrue(all('--offline' in argv and env['CONDA_OFFLINE']=='true' for argv,env in calls if argv[5:6] in (['create'],['search'])))

 def test_partial_install_and_runtime_failures_cannot_report_ready(self):
  for failure,status in (('install','install-failed'),('probe','verification-failed'),('curl-probe','verification-failed')):
   with self.subTest(failure=failure):
    result,summary,comparison,review,calls=self.run_stage(fail=failure)
    self.assertEqual(result,2);self.assertEqual(summary['status'],status)
    self.assertTrue(all('not verified' in row['note'] for row in comparison))

 def test_concurrent_source_edit_marks_comparison_stale(self):
  result,summary,comparison,review,calls=self.run_stage(change_source=True)
  self.assertEqual(result,2);self.assertEqual(summary['status'],'source-changed')
  self.assertFalse(summary['source_metadata_unchanged']);self.assertFalse(summary['promotion_performed'])

 def test_unreadable_final_source_inventory_still_produces_a_failed_review(self):
  result,summary,comparison,review,calls=self.run_stage(change_source='corrupt-metadata')
  self.assertEqual(result,2);self.assertEqual(summary['status'],'source-check-failed')
  self.assertIn('Cannot verify source metadata',' '.join(summary['issues']));self.assertIn('source-check-failed',review)

 def test_saved_stage_report_is_read_only_and_distinguishes_not_selected(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory)
   row={'package':'krb5','before_version':'1.21.3','before_build':'old','after_version':'','after_build':'',
        'status':'not-selected','note':'Not selected by dependency graph'}
   summary={'status':'ready-for-review','source_base':'/base','candidate_prefix':'/private/env',
            'comparison_counts':{'not-selected':1},'source_metadata_unchanged':True,'issues':[]}
   (root/'stage-summary.json').write_text(json.dumps(summary));(root/'comparison.json').write_text(json.dumps([row]))
   before={p.name:p.read_bytes() for p in root.iterdir()}
   with patch.object(m.subprocess,'run') as run,contextlib.redirect_stdout(io.StringIO()) as output:
    self.assertEqual(m.report_existing(root),0)
   run.assert_not_called();self.assertIn('krb5',output.getvalue());self.assertIn('not-selected',output.getvalue())
   self.assertEqual(before,{p.name:p.read_bytes() for p in root.iterdir()})


if __name__=='__main__':unittest.main()
