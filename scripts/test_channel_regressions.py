import importlib.util
import pathlib
import unittest
import tempfile, json, subprocess, io, os
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('maintenance',pathlib.Path(__file__).with_name('patch_miniforge_trust.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class DiagnosticTests(unittest.TestCase):
 def command(self,base,prefix):
  return [str(base/'bin/conda'),'install','-p',str(prefix),'--solver','classic','--json',
          '--override-channels','--channel','conda-forge','--strict-channel-priority',
          'conda-forge::python>=3.11','--yes']
 def test_saved_install_is_converted_to_dry_run(self):
  base=pathlib.Path('/test/base');prefix=base/'envs/example'
  argv=self.command(base,prefix)
  result=m.diagnostic_argv(base,prefix,argv,[])
  self.assertIn('--dry-run',result);self.assertNotIn('--yes',result)
  self.assertIn('--strict-channel-priority',result);self.assertIn('conda-forge::python>=3.11',result)
  self.assertIn('--yes',argv)
 def test_saved_commands_cannot_change_executable_prefix_or_channel_policy(self):
  base=pathlib.Path('/test/base');prefix=base/'envs/example'
  original=self.command(base,prefix)
  invalid=[['/different/conda']+original[1:],original+['--no-pin'],
           original+['--no-channel-priority'],original+['-p','/different/prefix'],
           [v for v in original if v!='--strict-channel-priority'],
           original+['defaults::openssl'],original+['--channel','defaults']]
  for argv in invalid:
   with self.subTest(argv=argv),self.assertRaises(RuntimeError):m.diagnostic_argv(base,prefix,argv,[])
 def test_diagnose_rejects_apply_before_any_environment_access(self):
  with patch.object(m.sys,'argv',['script','--diagnose','latest','--apply']),patch('sys.stderr',io.StringIO()),patch.object(m,'find_base') as find:
   with self.assertRaises(SystemExit):m.main()
   find.assert_not_called()
 def test_diagnostic_timeout_cli_defaults_and_custom_value(self):
  for extra,expected in (([],600),(['--diagnostic-timeout','1800'],1800)):
   with self.subTest(expected=expected),patch.object(m.sys,'argv',['script','--diagnose','latest']+extra),patch.object(m,'find_base',return_value=pathlib.Path('/base')),patch.object(m,'diagnose_existing',return_value=2) as diagnose:
    self.assertEqual(m.main(),2)
    diagnose.assert_called_once_with(pathlib.Path('latest'),pathlib.Path('/base'),False,expected)
 def test_diagnostic_timeout_rejects_invalid_values_or_wrong_mode(self):
  for argv in (['--diagnose','latest','--diagnostic-timeout','0'],['--diagnose','latest','--diagnostic-timeout','-1'],['--diagnostic-timeout','1800']):
   with self.subTest(argv=argv),patch.object(m.sys,'argv',['script']+argv),patch('sys.stderr',io.StringIO()),patch.object(m,'find_base') as find:
    with self.assertRaises(SystemExit):m.main()
    find.assert_not_called()
 def test_group_write_access_does_not_require_uid_ownership(self):
  prefix=unittest.mock.Mock()
  prefix.stat.return_value=unittest.mock.Mock(st_uid=2001,st_gid=2002,st_mode=0o40775)
  with patch.object(m.os,'geteuid',return_value=1000),patch.object(m,'groups',return_value={1000,2002}),patch.object(m.os,'access',return_value=True):
   self.assertTrue(m.maintainable(prefix))
 def test_diagnosis_runs_only_a_dry_run_and_writes_private_report(self):
  with tempfile.TemporaryDirectory() as directory:
   root=pathlib.Path(directory);base=root/'base';(base/'bin').mkdir(parents=True)
   (base/'bin/conda').touch();(base/'bin/python').touch();(base/'conda-meta').mkdir()
   (base/'etc/cse-trust/empty-ca-dir').mkdir(parents=True);(base/'etc/cse-trust/ca-bundle.pem').touch()
   marker=base/'conda-meta/history';marker.write_text('unchanged')
   logs=root/'logs';logs.mkdir();argv=self.command(base,base)
   (logs/'failed-command-001.json').write_text(json.dumps({'argv':argv,'phase':'install validated package plan'}))
   (logs/'summary.json').write_text(json.dumps([{'prefix':str(base),'command_failures':[{'file':'failed-command-001.json'}]}]))
   response={'success':False,'exception_name':'UnsatisfiableError','message':'Package python conflicts for: python_abi=3.14'}
   with patch.object(m,'capture',return_value=json.dumps({'pkgs_dirs':[str(root/'cache')]})),patch.object(m.subprocess,'run',return_value=subprocess.CompletedProcess([],1,json.dumps(response),'')) as run,patch.object(m,'atomic_write') as write,patch.object(m,'public_permissions') as permissions,patch('sys.stdout',io.StringIO()) as out:
    self.assertEqual(m.diagnose_existing(logs,base,True),2)
   command=run.call_args.args[0];env=run.call_args.kwargs['env']
   self.assertIn('--dry-run',command);self.assertNotIn('--yes',command);self.assertIn('-B',command)
   self.assertEqual(env['CONDA_DRY_RUN'],'true');self.assertEqual(env['CONDA_UNSATISFIABLE_HINTS'],'false')
   self.assertEqual(env['CONDA_SSL_VERIFY'],str(base/'etc/cse-trust/ca-bundle.pem'))
   self.assertEqual(marker.read_text(),'unchanged');write.assert_not_called();permissions.assert_not_called()
   reports=list(logs.glob('solver-diagnostic-*.json'));self.assertEqual(len(reports),1)
   self.assertEqual(reports[0].stat().st_mode&0o777,0o600)
   self.assertIn('Package python conflicts',out.getvalue())
 def test_foreign_owned_directory_permissions_are_left_to_owner(self):
  with tempfile.TemporaryDirectory() as directory:
   prefix=pathlib.Path(directory);original=pathlib.Path.lstat
   def foreign(path):
    value=original(path)
    if path==prefix:
     fields=list(value);fields[4]=m.os.geteuid()+1;return m.os.stat_result(fields)
    return value
   with patch.object(pathlib.Path,'lstat',foreign),patch.object(m,'maintenance_gid',return_value=m.os.getegid()),patch.object(m.os,'chmod') as chmod,patch.object(m.os,'chown') as chown:
    issues=m.public_permissions(prefix,prefix,True,lambda message:None)
    self.assertTrue(any('Owner must set group' in issue for issue in issues));chmod.assert_not_called();chown.assert_not_called()
 def test_timeout_keeps_partial_warning_and_reports_incomplete_analysis(self):
  with tempfile.TemporaryDirectory() as directory:
   root=pathlib.Path(directory);base=root/'base';(base/'bin').mkdir(parents=True)
   (base/'bin/conda').touch();(base/'conda-meta').mkdir()
   marker=base/'conda-meta/history';marker.write_text('unchanged')
   (base/'etc/cse-trust/empty-ca-dir').mkdir(parents=True);(base/'etc/cse-trust/ca-bundle.pem').touch()
   logs=root/'logs';logs.mkdir()
   (logs/'failed-command-001.json').write_text(json.dumps({'argv':self.command(base,base)}))
   (logs/'summary.json').write_text(json.dumps([{'prefix':str(base),'command_failures':[{'file':'failed-command-001.json'}]}]))
   warning=b'WARNING: Using .* with relational operator is superfluous and deprecated'
   expired=subprocess.TimeoutExpired('conda',7,output=b'',stderr=warning)
   with patch.object(m,'capture',return_value='{}'),patch.object(m.subprocess,'run',side_effect=expired) as run,patch('sys.stdout',io.StringIO()) as out:
    self.assertEqual(m.diagnose_existing(logs,base,True,timeout_seconds=7),2)
   self.assertEqual(run.call_args.kwargs['timeout'],7)
   report=json.loads(next(logs.glob('solver-diagnostic-*.json')).read_text())
   self.assertEqual(report['diagnostic_status'],'timed_out');self.assertEqual(report['timeout_seconds'],7)
   self.assertIsNone(report['returncode']);self.assertIn(warning.decode(),report['stderr'])
   self.assertEqual(marker.read_text(),'unchanged')
   self.assertLess(out.getvalue().index('DIAGNOSTIC TIMED OUT after 7 seconds'),out.getvalue().index(warning.decode()))
   self.assertIn('--diagnostic-timeout 1800',out.getvalue());self.assertIn('no conflict conclusion',out.getvalue())

class ClassicConflictTests(unittest.TestCase):
 def test_maintenance_disables_broken_hints_even_if_inherited_enabled(self):
  with patch.dict(os.environ,{'CONDA_UNSATISFIABLE_HINTS':'true'}):
   env=m.safe_environment()
   self.assertEqual(env['CONDA_UNSATISFIABLE_HINTS'],'false')
   self.assertEqual(os.environ['CONDA_UNSATISFIABLE_HINTS'],'true')
 def test_saved_type_error_identifies_conflict_reporting_crash(self):
  category,advice=m.failure_category("TypeError: unsupported operand type(s) for |: 'set' and 'tuple'")
  self.assertEqual(category,'Conda classic conflict-reporting bug')
  self.assertIn('dependency conflict',advice)
 @unittest.skipUnless(os.environ.get('CSE_CONDA_PYTHON'),'Set CSE_CONDA_PYTHON to an installed Conda Python for the real solver regression')
 def test_real_conda_conflict_path_rejects_without_type_error(self):
  probe='''
import json
from conda.resolve import Resolve
from conda.models.match_spec import MatchSpec
try:
    Resolve({}).find_conflicts({MatchSpec('python >=3.11')}, (MatchSpec('conda >=26.9.4'),))
except Exception as exc:
    print(json.dumps({'exception':type(exc).__name__,'message':str(exc)}))
else:
    raise AssertionError('Conflicting specifications were not rejected')
'''
  env=m.safe_environment();env['CONDA_JSON']='true';env['PYTHONDONTWRITEBYTECODE']='1'
  result=subprocess.run([os.environ['CSE_CONDA_PYTHON'],'-I','-c',probe],env=env,text=True,
                        stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True,timeout=30)
  self.assertEqual(json.loads(result.stdout)['exception'],'UnsatisfiableError',result.stdout+result.stderr)

class LibmambaRuntimeTests(unittest.TestCase):
 def test_only_install_and_probe_commands_use_the_restricted_runtime(self):
  base=pathlib.Path('/test/base')
  command=[base/'bin/conda','install','-p',base,'--solver','libmamba','--json','--dry-run']
  wrapped=m.solver_invocation(base,command)
  self.assertEqual(wrapped[:5],[str(base/'bin/python'),'-I','-B','-c',m.LIBMAMBA_CLI])
  self.assertEqual(wrapped[5:],list(map(str,command[1:])))
  self.assertEqual(m.solver_invocation(base,[base/'bin/conda','info','--json']),[str(base/'bin/conda'),'info','--json'])
 @unittest.skipUnless(os.environ.get('CSE_CONDA_PYTHON'),'Set CSE_CONDA_PYTHON to test the installed solver allowlist')
 def test_real_runtime_loads_only_the_explicit_solver_hook(self):
  result=subprocess.run([os.environ['CSE_CONDA_PYTHON'],'-I','-B','-c',m.LIBMAMBA_CLI,'__cse_solver_probe__'],
                        env=m.safe_environment(),text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True,timeout=30)
  data=json.loads(result.stdout);self.assertEqual(data['solver'],'libmamba')
  self.assertEqual(data['external_plugins'],['cse-libmamba-solver-only'])

class ChannelRegressionTests(unittest.TestCase):
 def test_host_only_installed_origin_ignored(self):
  for channel in ('https://conda.anaconda.org','https://conda.anaconda.org/','https://conda.anaconda.org/linux-64','conda.anaconda.org','None','None/linux-64'):
   with self.subTest(channel=channel):
    names,urls,flags,origins,excluded,unknown=m.environment_channels({'pip':{'channel':channel}},[],{})
    self.assertEqual(urls,['https://conda.anaconda.org/conda-forge']);self.assertEqual(origins,{});self.assertEqual(unknown,['pip'])
 def test_bad_channel_falls_back_to_actual_archive(self):
  record={'channel':'https://conda.anaconda.org','url':'https://conda.anaconda.org/bioconda/linux-64/pkg-1-0.conda'}
  self.assertEqual(m.recorded_origin(record),'https://conda.anaconda.org/bioconda')
 def test_invalid_subdir_does_not_strip_real_channel(self):
  self.assertEqual(m.recorded_origin({'channel':'https://conda.anaconda.org/conda-forge','subdir':'conda-forge'}),'https://conda.anaconda.org/conda-forge')
 def test_channel_object_location_is_preserved(self):
  self.assertEqual(m.recorded_origin({'channel':{'scheme':'https','location':'site.example/conda','name':'bioconda'}}),'https://site.example/conda/bioconda')
 def test_blank_structured_channel_uses_package_url(self):
  self.assertEqual(m.recorded_origin({'channel':{'location':'conda.anaconda.org','name':''},'url':'https://conda.anaconda.org/conda-forge/noarch/pkg-1-0.tar.bz2'}),'https://conda.anaconda.org/conda-forge')
 def test_channel_representation_is_not_a_repository(self):
  self.assertIsNone(m.recorded_origin({'channel':"Channel(auth=None, location='conda.anaconda.org', name='')"}))
 def test_mirror_label_and_file_channels_preserved(self):
  for channel,expected in [('https://mirror.example/bioconda/label/test/linux-64','https://mirror.example/bioconda/label/test'),('file:///opt/channels/local/noarch','file:///opt/channels/local'),('https://private.example','https://private.example')]:
   self.assertEqual(m.recorded_origin({'channel':channel}),expected)
 def test_explicit_blank_and_host_only_rejected_before_solve(self):
  for channel in ('','https://conda.anaconda.org','https://conda.anaconda.org/noarch','None/linux-64'):
   with self.assertRaisesRegex(RuntimeError,'Invalid requested channel'):m.requested_channels([channel],{})
 def test_normal_forge_default(self):
  names,urls,flags=m.requested_channels([],{})
  self.assertEqual(names,['conda-forge']);self.assertEqual(urls,['https://conda.anaconda.org/conda-forge']);self.assertEqual(flags,m.CHANNEL_ARGS)
 def test_bad_alias_mapping_rejected(self):
  for config in ({'custom_channels':{'conda-forge':None}},{'channel_alias':'conda.anaconda.org'}):
   with self.assertRaisesRegex(RuntimeError,'alias/custom location'):m.requested_channels([],config)
 def test_installed_channels_remain_per_environment(self):
  a=m.environment_channels({'a':{'channel':'bioconda'}},[],{})
  b=m.environment_channels({'b':{'channel':'nvidia'}},[],{})
  self.assertIn('https://conda.anaconda.org/bioconda',a[1]);self.assertNotIn('https://conda.anaconda.org/bioconda',b[1])
 def test_defaults_still_excluded(self):
  result=m.environment_channels({'a':{'channel':'defaults'},'b':{'channel':'conda-forge','url':'https://repo.anaconda.com/pkgs/main/linux-64/b.conda'}},[],{})
  self.assertEqual(result[1],['https://conda.anaconda.org/conda-forge']);self.assertEqual(len(result[4]),2)
 def test_origin_specs_preserved(self):
  self.assertEqual(m.qualify_specs(['pip>=26.2.2'],{'pip':'https://conda.anaconda.org/bioconda'}),['https://conda.anaconda.org/bioconda::pip>=26.2.2'])
 def test_channel_pins_and_site_mirrors(self):
  result=m.environment_channels({'pip':{'channel':'bioconda'}},[],{'pinned_packages':['bioconda::pip>=1']})
  self.assertTrue(m.allowed_pin_origin('bioconda',result[0],result[1],{}))
  self.assertEqual(m.requested_channels([],{'custom_channels':{'conda-forge':'https://site.example/conda'}})[1],['https://site.example/conda/conda-forge'])
 def test_pypi_metadata_not_inferred(self):
  for record in ({'channel':'pypi'},{'url':'https://files.pythonhosted.org/pkg.whl'},{}):self.assertIsNone(m.recorded_origin(record))

class StructuredChannelConfigTests(unittest.TestCase):
 def alias(self):
  return {'auth':None,'location':'conda.anaconda.org','name':'','package_filename':None,'platform':None,'scheme':'https','token':None}
 def test_reported_alias_object_with_blank_name(self):
  config={'channel_alias':self.alias()}
  self.assertEqual(m.requested_channels([],config)[1],['https://conda.anaconda.org/conda-forge'])
 def test_resolved_custom_object_does_not_duplicate_channel_name(self):
  channel=dict(self.alias(),name='conda-forge')
  config={'channel_alias':self.alias(),'custom_channels':{'conda-forge':channel}}
  self.assertEqual(m.requested_channels([],config)[1],['https://conda.anaconda.org/conda-forge'])
 def test_string_and_structured_config_are_equivalent(self):
  raw={'channel_alias':'https://mirror.example/base','custom_channels':{'conda-forge':'https://mirror.example/packages'}}
  resolved={'channel_alias':dict(self.alias(),location='mirror.example',name='base'),'custom_channels':{'conda-forge':dict(self.alias(),location='mirror.example/packages',name='conda-forge')}}
  self.assertEqual(m.requested_channels(['bioconda'],raw)[1],m.requested_channels(['bioconda'],resolved)[1])
 def test_structured_custom_label_suffix(self):
  config={'custom_channels':{'bioconda':dict(self.alias(),location='mirror.example/channels',name='bioconda')}}
  self.assertIn('https://mirror.example/channels/bioconda/label/test',m.requested_channels(['bioconda/label/test'],config)[1])
 def test_multichannel_entries_can_be_objects(self):
  config={'custom_multichannels':{'science':[dict(self.alias(),name='bioconda'),dict(self.alias(),name='nvidia')]}}
  self.assertEqual(m.requested_channels(['science'],config)[1],['https://conda.anaconda.org/conda-forge','https://conda.anaconda.org/bioconda','https://conda.anaconda.org/nvidia'])
 def test_auth_token_and_mirror_location_retained(self):
  value=dict(self.alias(),auth='user:secret',token='test-token',location='mirror.example/base',name='conda-forge')
  self.assertEqual(m.channel_value_url(value),'https://user:secret@mirror.example/base/t/test-token/conda-forge')
 def test_default_repository_still_blocked_in_objects(self):
  config={'custom_channels':{'conda-forge':dict(self.alias(),location='repo.anaconda.com',name='pkgs/main')}}
  with self.assertRaisesRegex(RuntimeError,'excluded Anaconda defaults'):m.requested_channels([],config)
 def test_alias_base_valid_but_installed_host_only_not_channel(self):
  value=self.alias();self.assertEqual(m.channel_value_url(value),'https://conda.anaconda.org')
  self.assertIsNone(m.recorded_origin({'channel':value}))

class ChannelFlowTests(unittest.TestCase):
 def test_preview_and_apply_with_host_only_record(self):
  for apply in (False,True):
   with self.subTest(apply=apply),tempfile.TemporaryDirectory() as directory:
    p=pathlib.Path(directory);base=p/'mf';(base/'bin').mkdir(parents=True);(base/'bin/conda').touch();(base/'conda-meta').mkdir();(base/'conda-meta/history').touch()
    record={'name':'ca-certificates','version':'2025.1.31','build':'0','channel':'https://conda.anaconda.org'}
    metadata=base/'conda-meta/ca.json';metadata.write_text(json.dumps(record));calls=[]
    def fake(cmd,**kw):
     calls.append(cmd)
     if '__cse_solver_probe__' in cmd:result={'success':True,'solver':'libmamba'}
     elif '--show' in cmd:result={'channel_alias':{'auth':None,'location':'conda.anaconda.org','name':'','package_filename':None,'platform':None,'scheme':'https','token':None},'custom_channels':{'conda-forge':{'auth':None,'location':'conda.anaconda.org','name':'conda-forge','platform':None,'scheme':'https','token':None}}}
     elif '--dry-run' in cmd:result={'success':True,'actions':{'LINK':[{'name':'ca-certificates','version':'2026.10.19','build':'0','channel':'conda-forge'}]}}
     elif 'install' in cmd:record['version']='2026.10.19';metadata.write_text(json.dumps(record));result={'success':True}
     elif '--explicit' in cmd:return subprocess.CompletedProcess(cmd,0,'@EXPLICIT\n','')
     else:result={'success':True}
     return subprocess.CompletedProcess(cmd,0,json.dumps(result),'')
    argv=['script',str(base),'--base-only','--log-dir',str(p/'logs')]+(['--apply'] if apply else [])
    with patch.object(m.sys,'argv',argv),patch.object(m.os,'geteuid',return_value=123),patch.object(m,'maintenance_gid',return_value=0),patch.object(m,'maintainable',return_value=True),patch.object(m,'choose_source',return_value=p/'source'),patch.object(m,'filtered_bundle',return_value=('PEM',[])),patch.object(m,'atomic_write',side_effect=lambda path,data:pathlib.Path(path).write_text(data)),patch.object(m.subprocess,'run',side_effect=fake),patch.object(m,'public_permissions',return_value=[]),patch('sys.stdout',io.StringIO()) as out:
     self.assertEqual(m.main(),0)
    row=json.loads((p/'logs/summary.json').read_text())[0]
    self.assertEqual(row['requested_channels'],['https://conda.anaconda.org/conda-forge']);self.assertEqual(row['unknown_package_origins'],['ca-certificates'])
    self.assertIn('No usable channel origin',out.getvalue());self.assertTrue(pathlib.Path(row['channel_records_file']).is_file())
    installs=[c for c in calls if 'install' in c];self.assertEqual(len(installs),2 if apply else 0)
    for cmd in installs:
     sources=[cmd[i+1] for i,value in enumerate(cmd) if value=='--channel']
     self.assertTrue(all(value in ('conda-forge','https://conda.anaconda.org/conda-forge') for value in sources))

class BaseUpdatePolicyTests(unittest.TestCase):
 def test_base_plan_unpins_applications_and_updates_conda(self):
  meta={n:{'version':v,'build':'0'} for n,v in [('conda','24.11.2'),('python','3.12.8'),('numpy','1.0'),('pip','24.3.1')]}
  targets,allowed,specs=m.plan_specs(meta,False,broad=True)
  self.assertIsNone(allowed);self.assertEqual(targets,set(meta));self.assertIn('numpy',specs);self.assertIn('python',specs);self.assertIn('conda>=26.9.4',specs);self.assertIn('pip>='+m.MINIMUM['pip'],specs)
 def test_other_prefix_retains_pins(self):
  meta={n:{'version':v,'build':'0'} for n,v in [('conda','24.11.2'),('python','3.12.8'),('numpy','1.0'),('pip','24.3.1')]}
  targets,allowed,specs=m.plan_specs(meta,False)
  self.assertIn('numpy=1.0=0',specs);self.assertIn('python=3.12.8=0',specs);self.assertIn('conda=24.11.2=0',specs)
 def test_broad_plan_accepts_numpy_matplotlib_kerberos(self):
  plan={'actions':{'LINK':[{'name':n} for n in ('numpy','matplotlib','matplotlib-base','krb5')]}}
  self.assertEqual(len(m.check_plan(plan,None)),4)
  with self.assertRaisesRegex(RuntimeError,'unrelated'):m.check_plan(plan,{'pip'})
 def test_broad_still_rejects_removal_or_defaults(self):
  for plan in ({'actions':{'UNLINK':[{'name':'certifi'}]}},{'actions':{'LINK':[{'name':'numpy','channel':'defaults'}]}}):
   with self.assertRaises(RuntimeError):m.check_plan(plan,None)
 def test_minimum_checks_reject_missing_or_old_packages(self):
  before={'pip':{'version':'24.3.1'},'certifi':{'version':'2024.12.14'}}
  for after in ({'pip':{'version':m.MINIMUM['pip']}},{'pip':{'version':'24.3.1'},'certifi':{'version':m.MINIMUM['certifi']}}):
   with self.assertRaises(RuntimeError):m.verify_minimums(before,after)
  after={n:{'version':m.MINIMUM[n]} for n in before}
  self.assertEqual(set(m.verify_minimums(before,after)),set(before))
 def run_update(self,broad,stale=False):
  with tempfile.TemporaryDirectory() as directory:
   p=pathlib.Path(directory);base=p/'mf';(base/'bin').mkdir(parents=True);(base/'bin/conda').touch()
   prefix=base if broad else p/'env';(prefix/'conda-meta').mkdir(parents=True);(prefix/'conda-meta/history').touch()
   installed={'ca-certificates':{'name':'ca-certificates','version':'2025.1.31','build':'0'},'numpy':{'name':'numpy','version':'1.0','build':'0'}}
   def save():
    for n,r in installed.items():(prefix/'conda-meta'/(n+'.json')).write_text(json.dumps(r))
   save();calls=[]
   links=[{'name':'ca-certificates','version':m.MINIMUM['ca-certificates'],'build':'0'}]+[{'name':n,'version':'2.0','build':'0'} for n in ('numpy','matplotlib','matplotlib-base','krb5')]
   def fake(cmd,**kw):
    calls.append(cmd)
    if '__cse_solver_probe__' in cmd:out={'success':True,'solver':'libmamba'}
    elif '--show' in cmd:out={}
    elif '--dry-run' in cmd:out={'success':True,'actions':{'LINK':links}}
    elif 'install' in cmd:
     for r in links:
      if not (stale and r['name']=='ca-certificates'):installed[r['name']]=dict(r)
     save();out={'success':True}
    elif '--explicit' in cmd:return subprocess.CompletedProcess(cmd,0,'@EXPLICIT\n','')
    else:out={'success':True}
    return subprocess.CompletedProcess(cmd,0,json.dumps(out),'')
   argv=['script',str(base),'--apply','--log-dir',str(p/'logs')]+(['--base-only'] if broad else ['--only',str(prefix)])
   with patch.object(m.sys,'argv',argv),patch.object(m.os,'geteuid',return_value=123),patch.object(m,'maintenance_gid',return_value=0),patch.object(m,'maintainable',return_value=True),patch.object(m,'choose_source',return_value=p/'source'),patch.object(m,'filtered_bundle',return_value=('PEM',[])),patch.object(m,'atomic_write',side_effect=lambda path,data:pathlib.Path(path).write_text(data)),patch.object(m.subprocess,'run',side_effect=fake),patch.object(m,'public_permissions',return_value=[]),patch('sys.stdout',io.StringIO()):result=m.main()
   return result,json.loads((p/'logs/summary.json').read_text())[0],[c for c in calls if 'install' in c]
 def test_full_base_flow_and_narrow_environment_flow(self):
  result,row,commands=self.run_update(True)
  self.assertEqual(result,0);self.assertEqual(row['status'],'updated');self.assertIn('--update-all',commands[0]);self.assertFalse(any('--freeze-installed' in c for c in commands));self.assertIn('ca-certificates',row['security_verification']);self.assertEqual(len(commands),2)
  result,row,commands=self.run_update(False)
  self.assertEqual(result,2);self.assertEqual(len(commands),1);self.assertIn('unrelated',' '.join(row['issues']))
 def test_stale_security_package_cannot_report_updated(self):
  result,row,commands=self.run_update(True,stale=True)
  self.assertEqual(result,2);self.assertEqual(row['status'],'incomplete');self.assertIn('below required minimum',' '.join(row['issues']))

class BaseTransactionTests(unittest.TestCase):
 def run_loaded_base(self,apply=True,current=False,fail_install=False,offline=False,stale_install=False,
                     available=None,default_scope=False,all_envs=False,only=False,stale_plan=False,
                     manager_stack=False,dry_run_install=False,missing_solver=False):
  with tempfile.TemporaryDirectory() as directory:
   root=pathlib.Path(directory);base=root/'loaded-miniforge'
   (base/'bin').mkdir(parents=True);(base/'bin/conda').touch()
   (base/'conda-meta').mkdir();(base/'conda-meta/history').touch()
   other=base/'envs/untouched';(other/'conda-meta').mkdir(parents=True)
   (other/'conda-meta/history').write_text('unchanged');(other/'.condarc').write_text('ssl_verify: /site/other.pem\n')
   (other/'ssl').mkdir();(other/'ssl/cert.pem').write_text('original PEM')
   original_other={str(p.relative_to(other)):p.read_bytes() for p in other.rglob('*') if p.is_file()}
   available=['26.9.4'] if available is None else available
   latest=max([v for v in available if v.replace('.','').isdigit()] or ['0'],key=m.version)
   installed={n:{'name':n,'version':v,'build':'0','channel':'conda-forge'} for n,v in
              [('conda',current if isinstance(current,str) else '26.9.4' if current else '24.11.2'),('ca-certificates','2024.12.14'),('certifi','2024.12.14'),('numpy','1.0')]}
   updates={'conda':max((installed['conda']['version'],latest),key=m.version),
            'ca-certificates':m.MINIMUM['ca-certificates'],'certifi':m.MINIMUM['certifi'],'numpy':'2.0'}
   if manager_stack:
    for name in ('mamba','libmamba','libmambapy','conda-libmamba-solver'):
     installed[name]={'name':name,'version':'1.5.12','build':'0','channel':'conda-forge'};updates[name]='2.5.0'
    for name,value in [('python','3.12.8'),('jupyter_core','5.7.2'),('libboost-python','1.85.0')]:
     installed[name]={'name':name,'version':value,'build':'old','channel':'conda-forge'}
     updates[name]={'python':'3.14.0','jupyter_core':'5.9.1','libboost-python':'1.88.0'}[name]
   def save():
    for name,record in installed.items():(base/'conda-meta'/(name+'.json')).write_text(json.dumps(record))
   save();calls=[]
   def fake(cmd,**kwargs):
    cmd=list(map(str,cmd));calls.append((cmd,dict(kwargs.get('env',{}))))
    if cmd[1:]==['info','--base']:return subprocess.CompletedProcess(cmd,0,str(base)+'\n','')
    if '__cse_solver_probe__' in cmd:output={'success':True,'solver':'classic' if missing_solver else 'libmamba'}
    elif '--show' in cmd:output={}
    elif 'search' in cmd:output={'conda':[{'name':'conda','version':v,'channel':'conda-forge','build':'0'} for v in available]}
    elif '--explicit' in cmd:return subprocess.CompletedProcess(cmd,0,'@EXPLICIT\n','')
    elif 'install' in cmd:
     if '--dry-run' in cmd:
      links=[dict(installed[n],version=v) for n,v in updates.items()]
      if stale_plan:links[0]['version']=installed['conda']['version']
      output={'success':True,'actions':{'LINK':links}}
     else:
      if dry_run_install:return subprocess.CompletedProcess(cmd,0,json.dumps({'success':True,'dry_run':True}),'')
      if fail_install:return subprocess.CompletedProcess(cmd,1,'','Package installation failed')
      if not stale_install:
       for name,value in updates.items():installed[name]['version']=value
      save();output={'success':True}
    elif '-c' in cmd:output={'python':[3,14,0],'packages':{},'bundles':{}}
    else:output={'success':True}
    return subprocess.CompletedProcess(cmd,0,json.dumps(output),'')
   scope=[] if default_scope else ['--all-envs'] if all_envs else ['--only',str(other)] if only else ['--base-only']
   argv=['patch_miniforge_trust.py']+scope+['--log-dir',str(root/'logs')]+(['--apply'] if apply else [])+(['--offline'] if offline else [])
   with patch.object(m.sys,'argv',argv),patch.dict(m.os.environ,{'CONDA_EXE':str(base/'bin/conda')}),patch.object(m.os,'geteuid',return_value=123),patch.object(m,'maintenance_gid',return_value=0),patch.object(m,'maintainable',return_value=True),patch.object(m,'choose_source',return_value=root/'source.pem'),patch.object(m,'filtered_bundle',return_value=('PEM',[])),patch.object(m,'atomic_write',side_effect=lambda path,data:pathlib.Path(path).write_text(data)),patch.object(m.subprocess,'run',side_effect=fake),patch.object(m,'public_permissions',return_value=[]),patch('sys.stdout',io.StringIO()):result=m.main()
   rows=json.loads((root/'logs/summary.json').read_text())
   self.assertEqual([r['prefix'] for r in rows],[str(other)] if only else [str(base),str(other)] if all_envs else [str(base)])
   if not all_envs and not only:
    self.assertFalse(any(str(other) in cmd for cmd,env in calls))
    self.assertEqual(original_other,{str(p.relative_to(other)):p.read_bytes() for p in other.rglob('*') if p.is_file()})
   return result,rows[0],calls,installed
 def test_old_conda_and_base_update_in_one_transaction(self):
  result,row,calls,installed=self.run_loaded_base(manager_stack=True)
  self.assertEqual(result,0,row['issues']);self.assertEqual(row['status'],'updated')
  installs=[cmd for cmd,env in calls if 'install' in cmd]
  self.assertEqual(len(installs),2);self.assertIn('--dry-run',installs[0]);self.assertIn('--update-all',installs[0])
  self.assertIn('libmamba',installs[0]);self.assertNotIn('--update-deps',installs[0])
  for name in ('python','jupyter_core','libboost-python','mamba'):
   self.assertIn(name,installs[0]);self.assertFalse(any('::'+name in value for value in installs[0]))
  self.assertEqual(installed['conda']['version'],'26.9.4');self.assertEqual(installed['numpy']['version'],'2.0')
  self.assertEqual(row['conda_update']['status'],'updated');self.assertNotIn('conda_bootstrap',row)
 def test_preview_is_local_and_does_not_load_solver_or_search(self):
  result,row,calls,installed=self.run_loaded_base(apply=False)
  self.assertEqual(result,0)
  self.assertFalse(any('install' in cmd or 'search' in cmd or '__cse_solver_probe__' in cmd for cmd,env in calls))
 def test_already_current_conda_still_updates_base(self):
  result,row,calls,installed=self.run_loaded_base(current=True)
  self.assertEqual(result,0,row['issues']);self.assertEqual(len([c for c,e in calls if 'install' in c]),2)
  self.assertEqual(installed['numpy']['version'],'2.0')
 def test_latest_available_conda_is_requested_and_cannot_be_downgraded(self):
  result,row,calls,installed=self.run_loaded_base(current=True,available=['26.9.4','26.11.0','27.0.0rc1'])
  self.assertEqual(result,0,row['issues']);self.assertEqual(installed['conda']['version'],'26.11.0')
  solve=next(c for c,e in calls if 'install' in c);self.assertIn('conda>=26.11.0',solve)
 def test_newer_installed_conda_is_retained(self):
  result,row,calls,installed=self.run_loaded_base(current='26.11.0',available=['26.9.4'])
  self.assertEqual(result,0,row['issues']);self.assertEqual(installed['conda']['version'],'26.11.0')
 def test_stale_plan_is_rejected_before_install(self):
  result,row,calls,installed=self.run_loaded_base(stale_plan=True)
  self.assertEqual(result,2);self.assertFalse(any('--yes' in c for c,e in calls))
  self.assertIn('conda=24.11.2',' '.join(row['issues']))
 def test_stale_installed_records_cannot_report_success(self):
  result,row,calls,installed=self.run_loaded_base(stale_install=True)
  self.assertEqual(result,2);self.assertEqual(row['conda_update']['status'],'incomplete')
  self.assertIn('below required minimum',' '.join(row['issues']))
 def test_install_error_is_reported_without_more_transactions(self):
  result,row,calls,installed=self.run_loaded_base(fail_install=True)
  self.assertEqual(result,2);self.assertEqual(installed['conda']['version'],'24.11.2')
  self.assertEqual(len([c for c,e in calls if 'install' in c]),2)
 def test_unexpected_dry_run_result_is_rejected(self):
  result,row,calls,installed=self.run_loaded_base(dry_run_install=True)
  self.assertEqual(result,2);self.assertIn('dry-run result for an install command',' '.join(row['issues']))
 def test_missing_solver_fails_before_search_or_install(self):
  result,row,calls,installed=self.run_loaded_base(missing_solver=True)
  self.assertEqual(result,2);self.assertFalse(any('install' in c or 'search' in c for c,e in calls))
  self.assertIn('libmamba',' '.join(row['issues']))
 def test_missing_or_stale_metadata_fails_before_install(self):
  for available in ([],['24.11.2'],['27.0.0rc1']):
   with self.subTest(available=available):
    result,row,calls,installed=self.run_loaded_base(available=available,offline=True)
    self.assertEqual(result,2);self.assertFalse(any('install' in c for c,e in calls))
 def test_offline_channels_plugins_and_tls_are_preserved(self):
  result,row,calls,installed=self.run_loaded_base(offline=True)
  self.assertEqual(result,0,row['issues'])
  for cmd,env in calls:
   if 'install' not in cmd:continue
   self.assertIn('--offline',cmd);self.assertIn('--override-channels',cmd);self.assertIn('--strict-channel-priority',cmd)
   self.assertEqual(env['CONDA_DRY_RUN'],'false');self.assertEqual(env['CONDA_NO_PLUGINS'],'true')
   self.assertTrue(env['CONDA_SSL_VERIFY'].endswith('/etc/cse-trust/ca-bundle.pem'))
 def test_default_scope_preserves_sibling_files(self):
  result,row,calls,installed=self.run_loaded_base(default_scope=True)
  self.assertEqual(result,0,row['issues'])
 def test_explicit_all_and_only_scope(self):
  for options in ({'all_envs':True},{'only':True}):
   result,row,calls,installed=self.run_loaded_base(apply=False,**options)
   self.assertEqual(result,0)
 def test_scan_requires_explicit_discovery_scope(self):
  with patch.object(m.sys,'argv',['script','--scan-root','/site']),patch('sys.stderr',io.StringIO()):
   with self.assertRaises(SystemExit):m.main()

if __name__=='__main__':unittest.main()
