import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import ssl
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('maintenance_user',Path(__file__).with_name('patch_miniforge_trust.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class UserVerificationTests(unittest.TestCase):
 def test_mode_needs_no_shared_write_access_or_cse_group(self):
  with patch.object(m.sys,'argv',['script','--verify-user','/home/user/check']),patch.object(m,'find_base',return_value=Path('/base')),patch.object(m,'verify_user_install',return_value=0) as verify,patch.object(m,'maintenance_gid') as group,patch.object(m,'maintainable') as writable:
   self.assertEqual(m.main(),0)
  group.assert_not_called();writable.assert_not_called();verify.assert_called_once()

 def test_mode_rejects_maintenance_and_offline_combinations(self):
  for option in (['--apply'],['--offline'],['--stage','/stage'],['--trust-only'],['--all-envs'],['--ca-bundle','/other.pem']):
   with self.subTest(option=option),patch.object(m.sys,'argv',['script','--verify-user','/home/user/check']+option),patch.object(m,'find_base') as find,patch('sys.stderr',io.StringIO()):
    with self.assertRaises(SystemExit):m.main()
    find.assert_not_called()

 def run_verification(self,fail=None,insecure=False,change_base=False,pip_settings='',blocked_root=False,chains=None):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory).resolve();base=root/'base';work=root/'home/check'
   (base/'conda-meta').mkdir(parents=True);(base/'bin').mkdir();(base/'ssl').mkdir()
   (base/'bin/python').touch();(base/'bin/conda').touch()
   ca=ssl.DER_cert_to_PEM_cert(ssl.create_default_context().get_ca_certs(binary_form=True)[0])
   (base/'ssl/cacert.pem').write_text(ca)
   installed={'python':{'name':'python','version':'3.12.8','build':'0'},'conda':{'name':'conda','version':m.CONDA_MINIMUM,'build':'0'}}
   for name,r in installed.items():(base/'conda-meta'/(name+'.json')).write_text(json.dumps(r))
   before={str(p.relative_to(base)):p.read_bytes() for p in base.rglob('*') if p.is_file()}
   calls=[];prefix=work/'env'
   selected={n:{'name':n,'version':v,'build':'0','channel':'conda-forge'} for n,v in [('python','3.12.9'),('pip',m.MINIMUM['pip']),('certifi',m.MINIMUM['certifi']),('ca-certificates',m.MINIMUM['ca-certificates']),('click','8.3.0'),('curl','8.23.0'),('libcurl','8.23.0')]}
   def fake(argv,**kwargs):
    argv=list(map(str,argv));calls.append((argv,dict(kwargs['env'])))
    if fail and fail in ' '.join(argv):return subprocess.CompletedProcess(argv,1,'','simulated download or build failure')
    if '--show' in argv:data={'ssl_verify':False if insecure else True}
    elif '-c' in argv and argv[argv.index('-c')+1]==m.USER_TRUST_AUDIT:
     data={'bundles':{},'ssl_paths':{},'default_ca_fingerprints':[]}
    elif argv[-2:]==['config','list']:return subprocess.CompletedProcess(argv,0,pip_settings,'')
    elif '--dry-run' in argv:data={'success':True,'actions':{'PREFIX':str(prefix),'LINK':list(selected.values())}}
    elif 'create' in argv or 'install' in argv and '-p' in argv:
     (prefix/'conda-meta').mkdir(parents=True,exist_ok=True);(prefix/'bin').mkdir(exist_ok=True);(prefix/'ssl').mkdir(exist_ok=True);(prefix/'lib').mkdir(exist_ok=True)
     (prefix/'ssl/cacert.pem').write_text(ca)
     for name,r in selected.items():(prefix/'conda-meta'/(name+'.json')).write_text(json.dumps(r))
     data={'success':True}
    elif '--report' in argv:
     Path(argv[argv.index('--report')+1]).write_text(json.dumps({'install':[{'download_info':{'url':'https://files.pythonhosted.org/packaging.whl'}}]}));data={}
    else:data={'prefix':str(prefix)}
    if change_base and '--report' in argv:(base/'.condarc').write_text('concurrent change')
    return subprocess.CompletedProcess(argv,0,json.dumps(data),'')
   args=SimpleNamespace(verify_user=work,channel=[],chains_dir=root/'chains' if chains else None)
   env={'PATH':os.environ['PATH']}
   roots={m.pem_entries(ca)[0][0]:'incident root'} if blocked_root else {}
   with patch.object(m.subprocess,'run',side_effect=fake),patch.object(m.Path,'home',return_value=root/'home'),patch.dict(m.ROOTS,roots,clear=blocked_root),patch.object(m,'verify_chains',side_effect=RuntimeError('UNSAFE: accepted local chain') if chains=='accepted' else None) as verify_chains,contextlib.redirect_stdout(io.StringIO()):
    result=m.verify_user_install(args,base,env)
   if chains:self.assertGreater(verify_chains.call_count,0)
   report=json.loads((work/'verification-summary.json').read_text())
   if not change_base:self.assertEqual(before,{str(p.relative_to(base)):p.read_bytes() for p in base.rglob('*') if p.is_file()})
   self.assertEqual(work.stat().st_mode&0o777,0o700)
   self.assertTrue(all(env['CONDA_PKGS_DIRS']==str(work/'pkgs') for argv,env in calls))
   self.assertTrue(all(env['CONDA_REGISTER_ENVS']=='false' for argv,env in calls))
   return result,report,calls

 def test_download_install_activation_and_build_checks_are_all_required(self):
  result,report,calls=self.run_verification()
  self.assertEqual(result,0,report['issues']);self.assertEqual(report['status'],'passed')
  for name in ('base-curl','base-curl-https','conda-create','conda-install','pip-download-install','pip-local-build','activation-imports','private-permissions','base-unchanged'):
   self.assertEqual(report['checks'][name]['status'],'passed')
  self.assertEqual(report['checks']['offline-chain-rejection']['status'],'not-tested')
  self.assertTrue(any('--no-cache-dir' in argv and '--report' in argv for argv,env in calls))
  self.assertTrue(any('wheel' in argv and '--no-build-isolation' in argv for argv,env in calls))
  self.assertFalse(any('emudhra' in ' '.join(argv).lower() for argv,env in calls))

 def test_download_failure_cannot_report_pass(self):
  result,report,calls=self.run_verification(fail='--report')
  self.assertEqual(result,2);self.assertEqual(report['status'],'failed')
  self.assertEqual(report['checks']['pip-download-install']['status'],'failed')

 def test_disabled_certificate_verification_stops_before_package_network(self):
  result,report,calls=self.run_verification(insecure=True)
  self.assertEqual(result,2);self.assertIn('verification is disabled',' '.join(report['issues']))
  self.assertFalse(any('create' in argv or '--report' in argv for argv,env in calls))

 def test_base_changes_fail_the_final_check(self):
  result,report,calls=self.run_verification(change_base=True)
  self.assertEqual(result,2);self.assertEqual(report['checks']['base-unchanged']['status'],'failed')

 def test_existing_or_live_destination_is_refused(self):
  with tempfile.TemporaryDirectory() as directory:
   base=Path(directory).resolve();args=SimpleNamespace(verify_user=base,channel=[],chains_dir=None)
   with self.assertRaisesRegex(RuntimeError,'new private directory'):m.verify_user_install(args,base,{})

 def test_pip_tls_bypass_and_outside_destination_fail_before_downloads(self):
  for settings in ("global.trusted-host='pypi.org'\n","install.target='/outside'\n","global.index-url='http://mirror.example/simple'\n"):
   with self.subTest(settings=settings):
    result,report,calls=self.run_verification(pip_settings=settings)
    self.assertEqual(result,2);self.assertFalse(any('create' in argv for argv,env in calls))

 def test_incident_root_fails_before_any_package_download(self):
  result,report,calls=self.run_verification(blocked_root=True)
  self.assertEqual(result,2);self.assertIn('incident roots remain',' '.join(report['issues']))
  self.assertFalse(any('create' in argv for argv,env in calls))

 def test_permission_or_activation_failure_cannot_pass(self):
  result,report,calls=self.run_verification(fail='--noprofile')
  self.assertEqual(result,2);self.assertEqual(report['checks']['activation-imports']['status'],'failed')

 def test_log_redaction_and_no_live_incident_test_hosts(self):
  text=m.redact_verification('https://user:secret@mirror.example/t/private-key/pkgs?token=secret')
  self.assertNotIn('secret',text);self.assertNotIn('private-key',text)
  with self.assertRaisesRegex(RuntimeError,'Incident test-site'):m.verification_source_url('https://dv-g3b-emudhra.we-have-a-problem.com')

 def test_requested_offline_chain_checks_are_required(self):
  result,report,calls=self.run_verification(chains='rejected')
  self.assertEqual(result,0);self.assertEqual(report['checks']['offline-chain-rejection']['status'],'passed')
  result,report,calls=self.run_verification(chains='accepted')
  self.assertEqual(result,2);self.assertEqual(report['checks']['offline-chain-rejection']['status'],'failed')

 def test_saved_report_does_not_rerun_commands_or_require_maintenance_group(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);(root/'verification-summary.json').write_text(json.dumps({'status':'passed','base':'/base','uid':123,'checks':{'conda-create':{'status':'passed'}},'issues':[]}))
   with patch.object(m.subprocess,'run') as run,patch.object(m,'maintenance_gid') as group,contextlib.redirect_stdout(io.StringIO()):
    self.assertEqual(m.report_existing(root),0)
   run.assert_not_called();group.assert_not_called()


if __name__=='__main__':unittest.main()
