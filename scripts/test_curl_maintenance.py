import importlib.util
import contextlib, io, json, os, ssl, subprocess, tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('maintenance_curl',Path(__file__).with_name('patch_miniforge_trust.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class CurlRequirementTests(unittest.TestCase):
 def test_stage_requests_the_executable_when_only_the_library_is_installed(self):
  meta={'libcurl':{'version':'8.16.0','build':'0'}}
  intent=m.base_package_intent(meta)
  roots,specs,omitted=m.stage_requests(meta,intent,[],m.CONDA_MINIMUM)
  self.assertIn('curl',roots);self.assertIn('curl',specs)

 def test_full_base_update_requests_curl_even_if_missing(self):
  meta={'libcurl':{'version':'8.16.0','build':'0'}}
  targets,allowed,specs=m.plan_specs(meta,True,broad=True)
  self.assertIn('curl',targets);self.assertIn('curl',specs)

 def test_required_curl_cannot_be_skipped(self):
  with self.assertRaisesRegex(RuntimeError,'Cannot omit required'):
   m.stage_requests({}, {'roots':[],'replacements':[]}, ['curl'], m.CONDA_MINIMUM)


class CurlRuntimeTests(unittest.TestCase):
 def test_system_fallback_and_mismatched_loaded_library_are_detected(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory).resolve();base=root/'base';(base/'bin').mkdir(parents=True);(base/'conda-meta').mkdir()
   binary=base/'bin/curl';system=root/'system';system.mkdir();(system/'curl').touch();(system/'curl').chmod(0o755)
   for name in ('curl','libcurl'):(base/'conda-meta'/(name+'.json')).write_text(json.dumps({'name':name,'version':'8.23.0','build':'0'}))
   scope={};exec(m.CURL_PROBE_SETUP,scope)
   def executable(libcurl):
    binary.write_text('#!/bin/sh\nprintf "%s\\n" "curl 8.23.0 (linux) libcurl/'+libcurl+' OpenSSL/3.5"\n');binary.chmod(0o755)
   executable('8.23.0')
   with patch.dict(os.environ,{'PATH':str(system)}):
    with self.assertRaisesRegex(RuntimeError,'PATH selects'):scope['curl_probe'](base,True)
   with patch.dict(os.environ,{'PATH':str(base/'bin')}):
    self.assertEqual(scope['curl_probe'](base,True)['loaded_libcurl'],'8.23.0')
    executable('8.16.0')
    with self.assertRaisesRegex(RuntimeError,'does not match installed'):scope['curl_probe'](base,True)
   binary.unlink()
   with self.assertRaisesRegex(RuntimeError,'libcurl alone'):scope['curl_probe'](base)


class CurlRepairTests(unittest.TestCase):
 def exercise(self,apply=True,unrelated=False,fail_runtime=False,real_trust=False,fail_https=False,curl_url=None,permission_notes=False):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory).resolve();base=root/'base';(base/'bin').mkdir(parents=True);(base/'conda-meta').mkdir()
   (base/'bin/python').touch();(base/'bin/conda').touch()
   if real_trust:
    (base/'ssl').mkdir()
    cert=next(ssl.DER_cert_to_PEM_cert(c) for c in ssl.create_default_context().get_ca_certs(binary_form=True) if m.hashlib.sha256(c).hexdigest().upper() not in m.ROOTS)
    (base/'ssl/cacert.pem').write_text(cert)
   installed={name:{'name':name,'version':value,'build':'0','channel':'conda-forge'} for name,value in
              [('python','3.12.9'),('conda',m.CONDA_MINIMUM),('numpy','2.0'),('libcurl','8.16.0'),('openssl','3.5.0')]}
   def save():
    for name,record in installed.items():(base/'conda-meta'/(name+'.json')).write_text(json.dumps(record))
   save();before=json.dumps(installed,sort_keys=True);calls=[]
   links=[{'name':name,'version':value,'build':'0','channel':'conda-forge','depends':deps} for name,value,deps in
          [('curl','8.23.0',['libcurl ==8.23.0 0']),('libcurl','8.23.0',['openssl >=3.5']),('openssl','3.5.1',[])]]
   if unrelated:links.append({'name':'numpy','version':'3.0','build':'0','channel':'conda-forge'})
   def fake(argv,**kwargs):
    values=argv[5:];calls.append((values,dict(kwargs['env'])))
    if argv[4]==m.CURL_HTTPS_PROBE:
     if fail_https:return subprocess.CompletedProcess(argv,1,'','curl: (60) SSL certificate problem at requested endpoint')
     result={'http_status':'200'}
    elif argv[4]==m.CURL_PROBE:
     if fail_runtime:return subprocess.CompletedProcess(argv,1,'','PATH selects /usr/bin/curl instead of Conda curl')
     result={'version':'8.23.0','loaded_libcurl':'8.23.0','selected_on_path':str(base/'bin/curl')}
    elif '--show' in values:result={}
    elif values[0]=='search':result={'curl':[{'version':'8.23.0'}]}
    elif '--dry-run' in values:result={'success':True,'actions':{'LINK':links}}
    else:
     for record in links:installed[record['name']]=record
     save();(base/'bin/curl').touch();result={'success':True}
    return subprocess.CompletedProcess(argv,0,json.dumps(result),'')
   args=SimpleNamespace(apply=apply,log_dir=root/'logs',channel=[],offline=False,ca_bundle=None,extra_ca=[],verbose=False,curl_url=curl_url)
   def permissions(*values):
    if not permission_notes:return []
    values[3]('SKIP PATH: foreign-owned directory requires owner review')
    values[4].append({'path':str(base/'bin/python'),'stage':'permissions','reason':'owner review','prefix':str(base)})
    return ['owner review']
   trust_patch=patch.object(m,'maintain_native_trust',wraps=m.maintain_native_trust) if real_trust else patch.object(m,'maintain_native_trust',return_value=0)
   with patch.object(m.subprocess,'run',side_effect=fake),patch.object(m,'maintenance_gid',return_value=os.getegid()),patch.object(m,'choose_source',return_value=root/'ca.pem'),patch.object(m,'filtered_bundle',return_value=('PEM',[])),patch.object(m,'permission_holds',return_value={}),patch.object(m,'public_permissions',side_effect=permissions) as perms,trust_patch as trust,contextlib.redirect_stdout(io.StringIO()) as output:
    result=m.repair_curl(args,base,m.safe_environment())
   row=json.loads((root/'logs/summary.json').read_text())[0]
   row['test_stdout']=output.getvalue()
   self.assertEqual(installed['python']['version'],'3.12.9');self.assertEqual(installed['numpy']['version'],'2.0')
   if not apply:self.assertEqual(json.dumps(installed,sort_keys=True),before)
   return result,row,calls,trust.call_count,perms.call_count
 def test_apply_installs_only_pair_and_dependencies_then_filters_and_checks(self):
  result,row,calls,trust,perms=self.exercise()
  self.assertEqual(result,0,row['issues']);self.assertEqual(row['status'],'updated')
  self.assertEqual(trust,1);self.assertEqual(perms,1)
  self.assertEqual(row['curl_repair']['runtime']['version'],'8.23.0')
  search=next(values for values,env in calls if values[:1]==['search'])
  self.assertNotIn('--strict-channel-priority',search)
  execution=next((values,env) for values,env in calls if '--yes' in values)
  self.assertNotIn('--update-all',execution[0]);self.assertNotIn('--prune',execution[0])
  self.assertEqual(set(json.loads(execution[1]['CSE_CONDA_PERMISSION_HOLDS'])['packages']),{'python','numpy','conda'})
  self.assertEqual(row['package_change_list']['evidence'],'verified-installed')
 def test_preview_changes_no_base_packages_or_permissions(self):
  result,row,calls,trust,perms=self.exercise(apply=False)
  self.assertEqual(result,0,row['issues']);self.assertEqual(row['status'],'previewed')
  self.assertFalse(any('--yes' in values for values,env in calls));self.assertEqual((trust,perms),(0,0))
 def test_unrelated_package_changes_stop_before_install(self):
  result,row,calls,trust,perms=self.exercise(unrelated=True)
  self.assertEqual(result,2);self.assertIn('unrelated',' '.join(row['issues']))
  self.assertFalse(any('--yes' in values for values,env in calls))
 def test_wrong_runtime_selection_does_not_report_success(self):
  result,row,calls,trust,perms=self.exercise(fail_runtime=True)
  self.assertEqual(result,2);self.assertEqual(row['status'],'incomplete')
  self.assertTrue(row['package_inventory_verified']);self.assertIn('PATH selects',' '.join(row['issues']))
 def test_native_trust_step_can_take_its_own_lock_during_repair(self):
  result,row,calls,trust,perms=self.exercise(real_trust=True)
  self.assertEqual(result,0,row['issues']);self.assertEqual(trust,1)
 def test_short_link_summaries_keep_installed_dependency_edges(self):
  meta={'libcurl':{'depends':['openssl >=3.5']},'openssl':{'depends':['libgcc >=14']}}
  plan={'actions':{'LINK':[{'name':'libcurl','version':'8.23.0'}]}}
  self.assertTrue({'curl','libcurl','openssl','libgcc'}<=m.curl_dependency_scope(meta,plan))
 def test_one_endpoint_failure_is_separate_from_verified_package_installation(self):
  url='https://user-service.example/download'
  result,row,calls,trust,perms=self.exercise(fail_https=True,curl_url=url)
  self.assertEqual(result,2);self.assertEqual(row['curl_repair']['packages'],'installed-and-verified')
  self.assertEqual(row['curl_repair']['https']['url'],url);self.assertEqual(row['curl_repair']['https']['status'],'failed')
  self.assertIn('Package installation: VERIFIED',row['test_stdout'])
 def test_permission_notes_are_logged_without_printing_each_skipped_path(self):
  result,row,calls,trust,perms=self.exercise(permission_notes=True)
  self.assertEqual(result,0);self.assertEqual(row['status'],'updated-with-skips')
  self.assertNotIn('SKIP PATH:',row['test_stdout']);self.assertIn('1 access/owner review notes',row['test_stdout'])


if __name__=='__main__':unittest.main()
