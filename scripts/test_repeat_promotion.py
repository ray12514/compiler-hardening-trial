"""Exercise repeated --promote through main, with real native certificate filtering."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import ssl
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('maintenance_repeat',Path(__file__).with_name('patch_miniforge_trust.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
fixtures=json.loads((Path(__file__).parent/'fixtures/emudhra-incident-certificates.json').read_text())['certificates']


class RepeatPromotionTests(unittest.TestCase):
 def fixture(self,root,with_curl=False):
  base=root/'base';(base/'bin').mkdir(parents=True);(base/'ssl').mkdir();(base/'conda-meta').mkdir()
  for name in ('python','conda'):(base/'bin'/name).touch()
  (base/'bin/python').chmod(0o755);(base/'conda-meta/history').write_text('installed rollout')
  bad=''.join(cert['pem'] for cert in fixtures)
  good=[ssl.DER_cert_to_PEM_cert(cert) for cert in ssl.create_default_context().get_ca_certs(binary_form=True)
        if not m.blocked_pem_entries(ssl.DER_cert_to_PEM_cert(cert))][:2]
  native=base/'ssl/cacert.pem';native.write_text(good[0]+bad);(base/'ssl/cert.pem').symlink_to('cacert.pem')
  source=root/'system.pem';source.write_text(good[1]+bad)
  installed={name:{'name':name,'version':value,'build':'0','subdir':'noarch','channel':'conda-forge','sha256':'c'*64,'md5':'d'*32,'depends':deps}
    for name,value,deps in [('conda',m.CONDA_MINIMUM,['python']),('python','3.12.9',[]),('conda-libmamba-solver','26.10.0',['python']),
      ('ca-certificates',m.MINIMUM['ca-certificates'],[]),('certifi',m.MINIMUM['certifi'],['python']),('pip',m.MINIMUM['pip'],['python']),
      ('numpy','2.0',['python']),('libcurl','8.23.0',['openssl >=3.5']),('openssl','3.5.0',[])]}
  curl={'name':'curl','version':'8.23.0','build':'0','subdir':'noarch','channel':'conda-forge','sha256':'e'*64,'md5':'f'*32,'depends':['libcurl ==8.23.0 0']}
  if with_curl:installed['curl']=curl;(base/'bin/curl').touch()
  def save(prefix,records):
   (prefix/'conda-meta').mkdir(parents=True,exist_ok=True)
   for item in (prefix/'conda-meta').glob('*.json'):item.unlink()
   for name,record in records.items():(prefix/'conda-meta'/(name+'.json')).write_text(json.dumps(record))
  save(base,installed)
  stage=root/'stage';save(stage/'env',installed);(stage/'pkgs').mkdir()
  # Legacy stage is already installed, and intentionally has no curl executable.
  summary={'status':'ready-for-review','source_base':str(base),'source_metadata_unchanged':True,'source_ca_unchanged':True,
           'source_state_after':{'packages':'old state','controls':{}},'requested_roots':sorted(installed),'conda_update':{'target':m.CONDA_MINIMUM}}
  (stage/'stage-summary.json').write_text(json.dumps(summary));(stage/'candidate-packages.json').write_text(json.dumps(installed))
  (stage/'candidate-plan.json').write_text(json.dumps({'success':True,'actions':{'LINK':list(installed.values())}}))
  return base,stage,installed,curl,save,source,good

 def run_command(self,root,base,stage,installed,curl,save,source,apply=False,number=0,unrelated=False,fail_https=False,chains=False):
  calls=[]
  def fake(argv,**kwargs):
   program=argv[4];values=argv[5:];calls.append(values)
   if program==m.CURL_PROBE:data={'version':'8.23.0','loaded_libcurl':'8.23.0','selected_on_path':str(base/'bin/curl')}
   elif program==m.CURL_HTTPS_PROBE:
    if fail_https:return subprocess.CompletedProcess(argv,1,'','curl: (60) certificate check failed for this endpoint')
    data={'http_status':'200'}
   elif '--show' in values:data={}
   elif values[:1]==['search']:raise AssertionError('Completed promotion must not search for newer versions')
   elif '--dry-run' in values:
    links=[curl]+([dict(installed['numpy'],version='3.0')] if unrelated else [])
    data={'success':True,'actions':{'LINK':links}}
   elif values[:1]==['install']:
    installed['curl']=curl;save(base,installed);(base/'bin/curl').touch();data={'success':True}
   else:raise AssertionError('Unexpected subprocess: '+str(values))
   return subprocess.CompletedProcess(argv,0,json.dumps(data),'')
  args=['script',str(base),'--promote',str(stage),'--log-dir',str(root/('logs-'+str(number)))]+(['--apply'] if apply else [])
  if chains:args+=['--chains-dir',str(root/'approved-chains')]
  before={str(p.relative_to(base)):p.read_bytes() for p in base.rglob('*') if p.is_file()}
  source_before=source.read_bytes();permission_calls=[]
  def permissions(*values):permission_calls.append(m.blocked_pem_entries((base/'ssl/cacert.pem').read_text()));return []
  with patch.object(m.sys,'argv',args),patch.object(m,'maintenance_gid',return_value=os.getegid()),patch.object(m,'maintainable',return_value=True),patch.object(m,'system_bundle',return_value=source),patch.object(m,'public_permissions',side_effect=permissions),patch.object(m.subprocess,'run',side_effect=fake),patch.object(m,'verify_chains') as verify_chains,contextlib.redirect_stdout(io.StringIO()) as output:
   result=m.main()
  if chains:
   verify_chains.assert_called_once()
   self.assertEqual(verify_chains.call_args.args[1],base/'ssl/cacert.pem')
  else:verify_chains.assert_not_called()
  log=root/('logs-'+str(number))/'repeat-promotion'
  row=json.loads((log/'summary.json').read_text())[0]
  if not apply:self.assertEqual(before,{str(p.relative_to(base)):p.read_bytes() for p in base.rglob('*') if p.is_file()})
  self.assertEqual(source.read_bytes(),source_before)
  return result,row,calls,output.getvalue(),permission_calls

 def test_same_promote_commands_preview_add_only_curl_then_apply_all_fixes_then_noop(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory).resolve();base,stage,installed,curl,save,source,good=self.fixture(root)
   original=json.loads(json.dumps(installed))
   result,row,calls,output,perms=self.run_command(root,base,stage,installed,curl,save,source)
   self.assertEqual(result,0,row['issues']);self.assertEqual([r['name'] for r in row['package_plan']],['curl']);self.assertFalse(perms)
   self.assertFalse(any('--yes' in call for call in calls));self.assertIn('Apply will merge/filter',output)
   result,row,calls,output,perms=self.run_command(root,base,stage,installed,curl,save,source,apply=True,number=1)
   self.assertEqual(result,0,row['issues']);self.assertEqual(row['promotion']['status'],'completed');self.assertEqual(perms,[{}])
   self.assertEqual({n:r for n,r in installed.items() if n!='curl'},original)
   self.assertEqual(set(dict(m.pem_entries((base/'ssl/cacert.pem').read_text()))),set(dict(m.pem_entries(''.join(good)))))
   self.assertFalse((base/'etc/cse-trust/use-ca.sh').exists());self.assertTrue((base/'ssl/cert.pem').is_symlink())
   result,row,calls,output,perms=self.run_command(root,base,stage,installed,curl,save,source,apply=True,number=2)
   self.assertEqual(result,0,row['issues']);self.assertEqual(row['package_plan'],[])
   self.assertFalse(any(call[:1] in (['install'],['search']) for call in calls));self.assertIn('no package transaction',output)
   self.assertEqual(row['package_change_list']['counts'],{'unchanged':len(installed)})
   with contextlib.redirect_stdout(io.StringIO()):self.assertEqual(m.export_package_changes(root/'logs-2/repeat-promotion',root/'exported-changes'),0)

 def test_existing_pair_rechecks_without_solve_or_reinstall(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory).resolve();base,stage,installed,curl,save,source,good=self.fixture(root,with_curl=True)
   result,row,calls,output,perms=self.run_command(root,base,stage,installed,curl,save,source,apply=True)
   self.assertEqual(result,0,row['issues']);self.assertFalse(any('--dry-run' in call or '--yes' in call for call in calls))

 def test_unrelated_solve_change_is_rejected_before_any_apply(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory).resolve();base,stage,installed,curl,save,source,good=self.fixture(root)
   before=(base/'ssl/cacert.pem').read_bytes()
   result,row,calls,output,perms=self.run_command(root,base,stage,installed,curl,save,source,apply=True,unrelated=True)
   self.assertEqual(result,2);self.assertIn('unrelated',' '.join(row['issues']));self.assertFalse(perms)
   self.assertFalse(any('--yes' in call for call in calls));self.assertEqual((base/'ssl/cacert.pem').read_bytes(),before)

 def test_repeat_promotion_keeps_requested_offline_chain_checks(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory).resolve();base,stage,installed,curl,save,source,good=self.fixture(root,with_curl=True)
   result,row,calls,output,perms=self.run_command(root,base,stage,installed,curl,save,source,apply=True,chains=True)
   self.assertEqual(result,0,row['issues']);self.assertEqual(row['offline-chain-rejection']['status'],'passed')

 def test_application_or_checksum_drift_does_not_reuse_a_completed_stage(self):
  for key,value in [('version','3.0'),('sha256','b'*64),('subdir','linux-64')]:
   with self.subTest(key=key),tempfile.TemporaryDirectory() as directory:
    base,stage,installed,curl,save,source,good=self.fixture(Path(directory).resolve())
    installed['numpy'][key]=value;save(base,installed)
    with self.assertRaisesRegex(RuntimeError,'changed since staging'):m.load_promotion(stage,base)

 def test_https_failure_preserves_verified_package_and_certificate_results(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory).resolve();base,stage,installed,curl,save,source,good=self.fixture(root,with_curl=True)
   result,row,calls,output,perms=self.run_command(root,base,stage,installed,curl,save,source,apply=True,fail_https=True)
   self.assertEqual(result,2);self.assertTrue(row['package_inventory_verified']);self.assertEqual(row['certificate_status']['mode'],'native-pem')
   self.assertFalse(m.blocked_pem_entries((base/'ssl/cacert.pem').read_text()))


if __name__=='__main__':unittest.main()
