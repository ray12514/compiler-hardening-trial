"""No-path promotion reviews must work on existing bases without old stage files."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import test_repeat_promotion as repeat_tests

spec=importlib.util.spec_from_file_location('maintenance_automatic',Path(__file__).with_name('patch_miniforge_trust.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class AutomaticPromotionTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name).resolve()
  self.base,stage,self.installed,self.curl,self.save,self.source,self.good=repeat_tests.RepeatPromotionTests().fixture(self.root)
  shutil.rmtree(stage)  # Teammate no longer has the old stage, or any maintenance marker.
  self.home=self.root/'home';self.home.mkdir();self.calls=[];self.permission_checks=[];self.fail_preview=False
  self.changed_execution_hash=False
  self.stack=contextlib.ExitStack();self.addCleanup(self.stack.close)
  self.stack.enter_context(patch.object(m.Path,'home',return_value=self.home))
  self.stack.enter_context(patch.object(m,'maintenance_gid',return_value=os.getegid()))
  self.stack.enter_context(patch.object(m,'maintainable',return_value=True))
  self.stack.enter_context(patch.object(m,'find_base',return_value=self.base))
  self.stack.enter_context(patch.object(m,'system_bundle',return_value=self.source))
  self.stack.enter_context(patch.object(m,'public_permissions',side_effect=self.permissions))
  self.stack.enter_context(patch.object(m.subprocess,'run',side_effect=self.fake_cli))
  self.stage=self.stack.enter_context(patch.object(m,'stage_base',side_effect=AssertionError('Updated base must not restage')))

 def permissions(self,*args):
  self.permission_checks.append(m.blocked_pem_entries((self.base/'ssl/cacert.pem').read_text()));return []

 def fake_cli(self,argv,**kwargs):
  program=argv[4];values=argv[5:];self.calls.append((values,dict(kwargs['env'])))
  if program==m.CURL_PROBE:data={'version':'8.23.0','loaded_libcurl':'8.23.0','selected_on_path':str(self.base/'bin/curl')}
  elif program==m.CURL_HTTPS_PROBE:data={'http_status':'200'}
  elif '--show' in values:data={}
  elif '--dry-run' in values:
   if self.fail_preview:return subprocess.CompletedProcess(argv,1,'','review solve failed')
   data={'success':True,'actions':{'LINK':[self.curl]}}
  elif values[:1]==['install']:
   self.assertIn('CSE_CONDA_APPROVED_PLAN',kwargs['env'])
   guard=json.loads(Path(kwargs['env']['CSE_CONDA_APPROVED_PLAN']).read_text())
   self.assertEqual(guard['packages']['curl']['sha256'],self.curl['sha256'])
   self.installed['curl']=dict(self.curl)
   if self.changed_execution_hash:self.installed['curl']['sha256']='a'*64
   self.save(self.base,self.installed);(self.base/'bin/curl').touch();data={'success':True}
  else:raise AssertionError('Unexpected subprocess: '+str(values))
  return subprocess.CompletedProcess(argv,0,json.dumps(data),'')

 def command(self,*values):
  with contextlib.redirect_stdout(io.StringIO()) as output:result=m.main(list(values))
  return result,output.getvalue()

 def pointer(self):return m.approval_scope(self.base)/'latest.json'
 def review_root(self):return Path(json.loads(self.pointer().read_text())['directory'])

 def test_teammate_can_review_then_apply_without_any_old_path_or_rebuild(self):
  old=json.loads(json.dumps(self.installed));native=(self.base/'ssl/cacert.pem').read_bytes();source=self.source.read_bytes()
  result,output=self.command('--promote');self.assertEqual(result,0,output)
  root=self.review_root();self.assertIn(str(root),output);self.assertIn('no old stage needed',output)
  self.assertEqual(self.installed,old);self.assertEqual((self.base/'ssl/cacert.pem').read_bytes(),native);self.assertFalse(self.permission_checks)
  self.assertEqual(root.stat().st_mode&0o777,0o700);self.assertEqual((root/'review.json').stat().st_mode&0o777,0o600)
  review=json.loads((root/'review.json').read_text());self.assertEqual(review['kind'],'maintenance')
  self.assertEqual([row['name'] for row in review['plan']['actions']['LINK']],['curl'])
  self.assertFalse(any('--yes' in values for values,env in self.calls));self.calls.clear()
  result,output=self.command('--promote','--apply');self.assertEqual(result,0,output)
  self.assertFalse(any('--dry-run' in values or 'search' in values for values,env in self.calls))
  self.assertEqual({n:r for n,r in self.installed.items() if n!='curl'},old)
  self.assertEqual(self.permission_checks,[{}]);self.assertFalse(m.blocked_pem_entries((self.base/'ssl/cacert.pem').read_text()))
  self.assertEqual(self.source.read_bytes(),source);self.assertEqual(json.loads(self.pointer().read_text())['status'],'applied')
  self.assertTrue((root/'review.json').is_file());self.stage.assert_not_called()

 def test_saved_review_can_be_reported_without_module_access_or_network(self):
  self.assertEqual(self.command('--promote')[0],0);root=self.review_root();self.calls.clear()
  with patch.object(m,'find_base',side_effect=AssertionError('No module lookup')):
   result,output=self.command('--report',str(root))
  self.assertEqual(result,0);self.assertIn('SAVED AUTOMATIC REVIEW',output);self.assertFalse(self.calls)

 def test_every_review_is_new_and_existing_custom_file_or_directory_is_preserved(self):
  self.assertEqual(self.command('--promote')[0],0);first=self.review_root();original=(first/'review.json').read_bytes()
  self.assertEqual(self.command('--promote')[0],0);self.assertNotEqual(self.review_root(),first);self.assertEqual((first/'review.json').read_bytes(),original)
  custom=self.root/'named-review';custom.write_text('keep existing file')
  self.assertEqual(self.command('--approve','--log-dir',str(custom))[0],0)
  self.assertEqual(custom.read_text(),'keep existing file');self.assertNotEqual(self.review_root(),custom)
  existing=self.root/'existing-dir';existing.mkdir();(existing/'keep').write_text('keep existing directory')
  self.assertEqual(self.command('--promote','--log-dir',str(existing))[0],0)
  self.assertEqual((existing/'keep').read_text(),'keep existing directory');self.assertNotEqual(self.review_root(),existing)
  link=self.root/'dangling-review';link.symlink_to(self.root/'do-not-create')
  self.assertEqual(self.command('--promote','--log-dir',str(link))[0],0)
  self.assertTrue(link.is_symlink());self.assertFalse((self.root/'do-not-create').exists())

 def test_no_review_or_a_review_for_another_base_does_not_apply(self):
  with self.assertRaisesRegex(RuntimeError,'run --promote first'):self.command('--promote','--apply')
  self.assertEqual(self.command('--promote')[0],0)
  other=self.root/'other-base';other.mkdir()
  with patch.object(m,'find_base',return_value=other),self.assertRaisesRegex(RuntimeError,'run --promote first'):
   self.command('--promote','--apply')
  self.assertFalse(any('--yes' in values for values,env in self.calls))

 def test_base_or_os_source_changes_require_a_new_review(self):
  for change in ('package','system-ca'):
   with self.subTest(change=change):
    self.assertEqual(self.command('--promote')[0],0)
    if change=='package':self.installed['numpy']['version']='2.1';self.save(self.base,self.installed)
    else:self.source.write_text(self.source.read_text()+'\n')
    with self.assertRaisesRegex(RuntimeError,'changed since review'):self.command('--promote','--apply')
  self.assertFalse(any('--yes' in values for values,env in self.calls))

 def test_failed_new_review_does_not_fall_back_to_an_older_ready_review(self):
  self.assertEqual(self.command('--promote')[0],0);first=self.review_root();self.fail_preview=True
  result,output=self.command('--promote');self.assertEqual(result,2,output);self.assertNotEqual(first,self.review_root())
  with self.assertRaisesRegex(RuntimeError,'not ready'):self.command('--promote','--apply')

 def test_tampered_saved_review_and_options_are_rejected(self):
  self.assertEqual(self.command('--promote')[0],0)
  with self.assertRaisesRegex(RuntimeError,'Options differ'):self.command('--promote','--apply','--channel','another-channel')
  file=self.review_root()/'review.json';file.write_text(file.read_text()+'\n')
  with self.assertRaisesRegex(RuntimeError,'review changed'):self.command('--promote','--apply')

 def test_hash_mismatch_after_install_is_not_reported_as_complete(self):
  self.assertEqual(self.command('--promote')[0],0);self.changed_execution_hash=True
  result,output=self.command('--promote','--apply');self.assertEqual(result,2,output)
  self.assertIn('checksums/platforms differ',output);self.assertFalse(self.permission_checks)

 def test_after_success_another_review_and_apply_skip_all_package_transactions(self):
  self.assertEqual(self.command('--promote')[0],0);self.assertEqual(self.command('--promote','--apply')[0],0)
  self.calls.clear();self.assertEqual(self.command('--promote')[0],0)
  self.assertEqual(self.command('--promote','--apply')[0],0)
  self.assertFalse(any(values[:1]==['install'] or 'search' in values for values,env in self.calls))


class AutomaticInitialRolloutTests(unittest.TestCase):
 def test_missing_minimum_automatically_stages_and_previews_with_new_directories(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory).resolve();home=root/'home';home.mkdir();base=root/'base';base.mkdir()
   args=['--promote']
   def fake_stage(args,selected,env):
    self.assertEqual(selected,base);self.assertFalse(args.stage.exists());args.stage.mkdir()
    for name in ('candidate-packages.json','candidate-plan.json','stage-summary.json'):(args.stage/name).write_text('{}')
    return 0
   # The existing stage_base and explicit promotion integration tests cover those
   # implementations; this exercises automatic orchestration without new flags.
   original=m.main
   nested=[]
   def dispatch(argv=None):
    if argv and '--log-dir' in argv:nested.append(argv);return 0
    return original(argv)
   with patch.object(m.Path,'home',return_value=home),patch.object(m,'find_base',return_value=base),patch.object(m,'maintenance_gid',return_value=os.getegid()),patch.object(m,'maintainable',return_value=True),patch.object(m,'records',return_value={}),patch.object(m,'approval_snapshot',return_value={'base_state':'unchanged'}),patch.object(m,'stage_base',side_effect=fake_stage) as stage,patch.object(m,'main',side_effect=dispatch),contextlib.redirect_stdout(io.StringIO()):
    self.assertEqual(original(args),0)
   stage.assert_called_once();self.assertEqual(len(nested),1);self.assertIn('--promote',nested[0]);self.assertNotIn('--apply',nested[0])

 def test_real_initial_staging_preview_and_apply_are_automatic(self):
  import test_promote_miniforge as promotion_tests
  import test_repeat_promotion as repeat_tests
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory).resolve();home=root/'home';home.mkdir()
   base,old_stage,before,after,summary,save=promotion_tests.PromotionTests().fixture(root)
   shutil.rmtree(old_stage);installed=dict(before);after['old-runtime']=dict(before['old-runtime'])
   bad=''.join(cert['pem'] for cert in repeat_tests.fixtures)
   good=next(m.ssl.DER_cert_to_PEM_cert(cert) for cert in m.ssl.create_default_context().get_ca_certs(binary_form=True)
             if not m.blocked_pem_entries(m.ssl.DER_cert_to_PEM_cert(cert)))
   (base/'ssl').mkdir();(base/'ssl/cacert.pem').write_text(good+bad)
   source=root/'os.pem';source.write_text(good+bad);source_before=source.read_bytes();calls=[]
   original={str(p.relative_to(base)):p.read_bytes() for p in base.rglob('*') if p.is_file()}
   def fake(argv,**kwargs):
    program=argv[4];values=argv[5:];calls.append(values)
    runtime=Path(argv[0]).parent.parent
    if program==m.CURL_PROBE:data={'version':'8.23.0','loaded_libcurl':'8.23.0'}
    elif program==m.AUDIT:
     meta=m.records(runtime)
     data={'python':[3,14,10],'packages':{'pip':meta['pip']['version'],'certifi':meta['certifi']['version']},'bundles':{}}
    elif values[:1]==['__cse_solver_probe__']:data={'solver':'libmamba','success':True}
    elif '--show' in values:data={}
    elif values[:1]==['search']:data={'conda':[{'version':m.CONDA_MINIMUM}]}
    elif '--explicit' in values:return subprocess.CompletedProcess(argv,0,'@EXPLICIT\n','')
    elif values[:1]==['info']:data={'platform':'linux-64'}
    elif values[:1]==['create']:
     if '--dry-run' in values:data={'success':True,'actions':{'LINK':list(after.values())}}
     else:
      candidate=Path(values[values.index('-p')+1]);save(candidate,after)
      (candidate/'bin').mkdir();(candidate/'bin/python').touch();(candidate/'bin/conda').touch()
      (candidate/'ssl').mkdir();(candidate/'ssl/cacert.pem').write_text(good+bad)
      data={'success':True}
    elif values[:1]==['install']:
     if '--dry-run' in values:data={'success':True,'actions':{'LINK':list(after.values()),'UNLINK':list(before.values())}}
     else:installed.clear();installed.update(after);save(base,installed);(base/'bin/curl').touch();data={'success':True}
    else:data={'success':True}
    return subprocess.CompletedProcess(argv,0,json.dumps(data),'')
   with patch.object(m.Path,'home',return_value=home),patch.object(m,'find_base',return_value=base),patch.object(m,'maintenance_gid',return_value=os.getegid()),patch.object(m,'maintainable',return_value=True),patch.object(m,'system_bundle',return_value=source),patch.object(m,'public_permissions',return_value=[]),patch.object(m.subprocess,'run',side_effect=fake),contextlib.redirect_stdout(io.StringIO()) as output:
    self.assertEqual(m.main(['--promote']),0,output.getvalue())
    pointer=m.approval_scope(base)/'latest.json';review_dir=Path(json.loads(pointer.read_text())['directory'])
    review=json.loads((review_dir/'review.json').read_text());self.assertEqual(review['kind'],'stage')
    self.assertEqual(original,{str(p.relative_to(base)):p.read_bytes() for p in base.rglob('*') if p.is_file()})
    self.assertEqual(m.main(['--promote','--apply']),0,output.getvalue())
   self.assertEqual(installed,after);self.assertEqual(source.read_bytes(),source_before)
   self.assertFalse(m.blocked_pem_entries((base/'ssl/cacert.pem').read_text()))
   self.assertEqual(len([call for call in calls if call[:1]==['create']]),2)  # One dry run and one private install.



if __name__=='__main__':unittest.main()
