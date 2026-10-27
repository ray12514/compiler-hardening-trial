import importlib.util
import pathlib
import unittest
import tempfile, json, subprocess, io
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('maintenance',pathlib.Path(__file__).with_name('patch_miniforge_trust.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

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
     if '--show' in cmd:result={'channel_alias':{'auth':None,'location':'conda.anaconda.org','name':'','package_filename':None,'platform':None,'scheme':'https','token':None},'custom_channels':{'conda-forge':{'auth':None,'location':'conda.anaconda.org','name':'conda-forge','platform':None,'scheme':'https','token':None}}}
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
    if '--show' in cmd:out={}
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

class CondaBootstrapTests(unittest.TestCase):
 def test_bootstrap_relaxes_installer_history_for_runtime_dependency_closure(self):
  meta={'conda':{'depends':['requests >=2','python >=3.11']},
        'python':{'depends':['libgcc >=15']},'requests':{'depends':['urllib3 >=2']},
        'urllib3':{'depends':[]},'libgcc':{'depends':['libgomp >=15']},
        'libgomp':{'depends':['libgcc >=15']},'numpy':{'depends':['python >=3.11']}}
  self.assertEqual(m.bootstrap_dependencies(meta),set(meta)-{'numpy'})
 def run_loaded_base(self,apply=True,current=False,fail_bootstrap=False,offline=False,stale_bootstrap=False,
                     available=None,default_scope=False,all_envs=False,only=False,downgrade_full=False,manager_stack=False,
                     stale_plan=False,dry_run_install=False):
  with tempfile.TemporaryDirectory() as directory:
   root=pathlib.Path(directory);base=root/'loaded-miniforge'
   (base/'bin').mkdir(parents=True);(base/'bin/conda').touch()
   (base/'conda-meta').mkdir();(base/'conda-meta/history').touch()
   other=base/'envs/untouched';(other/'conda-meta').mkdir(parents=True)
   (other/'conda-meta/history').write_text('unchanged')
   (other/'.condarc').write_text('ssl_verify: /site/other.pem\n')
   (other/'ssl').mkdir();(other/'ssl/cert.pem').write_text('original PEM')
   original_other={str(p.relative_to(other)):p.read_bytes() for p in other.rglob('*') if p.is_file()}
   available=['26.9.4'] if available is None else available
   latest=max([v for v in available if v.replace('.','').isdigit()] or ['0'],key=m.version)
   minimums={'conda':latest,'ca-certificates':m.MINIMUM['ca-certificates'],'certifi':m.MINIMUM['certifi']}
   installed={n:{'name':n,'version':v,'build':'0','channel':'conda-forge'} for n,v in
              [('conda',current if isinstance(current,str) else '26.9.4' if current else '24.11.2'),('ca-certificates','2025.1.31'),('certifi','2025.1.31'),('numpy','1.0')]}
   if manager_stack:
    for name in ('mamba','libmamba','libmambapy','conda-libmamba-solver'):
     installed[name]={'name':name,'version':'1.5.12','build':'0','channel':'conda-forge'}
     minimums[name]='2.5.0'
    installed['python']={'name':'python','version':'3.12.9','build':'0','channel':'conda-forge'}
    minimums['python']='3.14.0'
   def save():
    for name,record in installed.items():(base/'conda-meta'/(name+'.json')).write_text(json.dumps(record))
   save();calls=[]
   def fake(cmd,**kwargs):
    cmd=list(map(str,cmd));calls.append((cmd,dict(kwargs.get('env',{}))))
    if cmd[1:]==['info','--base']:return subprocess.CompletedProcess(cmd,0,str(base)+'\n','')
    if '--show' in cmd:output={}
    elif 'search' in cmd:output={'conda':[{'name':'conda','version':v,'channel':'conda-forge','build':'0'} for v in available]}
    elif '-c' in cmd:output={'python':[3,12,9],'packages':{},'bundles':{}}
    elif '--explicit' in cmd:return subprocess.CompletedProcess(cmd,0,'@EXPLICIT\n','')
    elif 'install' in cmd:
     is_old=m.version(installed['conda']['version'])<m.version('26.9.4')
     if '--update-all' in cmd and is_old:
      return subprocess.CompletedProcess(cmd,1,'','Conda must be updated before solving the base package update')
     if '--dry-run' in cmd:
      links=[dict(installed[n],version=v) for n,v in minimums.items()]
      if m.version(installed['conda']['version'])>m.version(latest):links[0]['version']=installed['conda']['version']
      if stale_plan:links[0]['version']=installed['conda']['version']
      if '--update-all' in cmd and downgrade_full:links[0]['version']=m.CONDA_MINIMUM
      if '--update-all' in cmd:links.append(dict(installed['numpy'],version='2.0'))
      output={'success':True,'actions':{'LINK':links}}
     else:
      if dry_run_install:return subprocess.CompletedProcess(cmd,0,json.dumps({'success':True,'dry_run':True}),'')
      if is_old and fail_bootstrap:return subprocess.CompletedProcess(cmd,1,'','Conda bootstrap installation failed')
      for name,value in minimums.items():
       if name=='conda' and m.version(installed[name]['version'])>m.version(value):continue
       if not (is_old and stale_bootstrap):installed[name]['version']=value
      if any('numpy=2.0=' in value for value in cmd):installed['numpy']['version']='2.0'
      save();output={'success':True}
    else:output={'success':True}
    return subprocess.CompletedProcess(cmd,0,json.dumps(output),'')
   scope=[] if default_scope else ['--all-envs'] if all_envs else ['--only',str(other)] if only else ['--base-only']
   argv=['patch_miniforge_trust.py']+scope+['--log-dir',str(root/'logs')]+(['--apply'] if apply else [])+(['--offline'] if offline else [])
   with patch.object(m.sys,'argv',argv),patch.dict(m.os.environ,{'CONDA_EXE':str(base/'bin/conda')}),patch.object(m.os,'geteuid',return_value=123),patch.object(m,'maintenance_gid',return_value=0),patch.object(m,'maintainable',return_value=True),patch.object(m,'choose_source',return_value=root/'source.pem'),patch.object(m,'filtered_bundle',return_value=('PEM',[])),patch.object(m,'atomic_write',side_effect=lambda path,data:pathlib.Path(path).write_text(data)),patch.object(m.subprocess,'run',side_effect=fake),patch.object(m,'public_permissions',return_value=[]),patch('sys.stdout',io.StringIO()):
    result=m.main()
   rows=json.loads((root/'logs/summary.json').read_text())
   self.assertEqual([r['prefix'] for r in rows],[str(other)] if only else [str(base),str(other)] if all_envs else [str(base)])
   if not all_envs and not only:
    self.assertFalse(any(str(other) in cmd for cmd,env in calls))
    self.assertEqual(original_other,{str(p.relative_to(other)):p.read_bytes() for p in other.rglob('*') if p.is_file()})
   summary=rows[0]
   return result,summary,calls,installed,json.loads((root/'logs/certificate-status.json').read_text())
 def test_loaded_old_conda_is_upgraded_before_full_base_solve(self):
  result,row,calls,installed,cert=self.run_loaded_base()
  self.assertEqual(result,0,row['issues']);self.assertEqual(row['status'],'updated')
  installs=[(cmd,env) for cmd,env in calls if 'install' in cmd]
  self.assertEqual(len(installs),4)
  self.assertNotIn('--update-all',installs[0][0]);self.assertIn('--dry-run',installs[0][0])
  self.assertIn('--update-all',installs[2][0]);self.assertIn('--dry-run',installs[2][0])
  self.assertEqual(installed['conda']['version'],'26.9.4');self.assertEqual(installed['numpy']['version'],'2.0')
  self.assertEqual(row['conda_bootstrap']['status'],'updated');self.assertEqual(cert['status'],'written')
  self.assertTrue(any(change['name']=='conda' and change['before']=='24.11.2' for change in row['package_changes']))
  for cmd,env in installs:
   self.assertTrue(env['CONDA_SSL_VERIFY'].endswith('/etc/cse-trust/ca-bundle.pem'))
   self.assertEqual(env['REQUESTS_CA_BUNDLE'],env['CONDA_SSL_VERIFY'])
   self.assertEqual(env['CONDA_DRY_RUN'],'false')
   self.assertNotIn('ssl_verify=false',' '.join(cmd).lower())
   self.assertNotIn('miniforge3',' '.join(cmd));self.assertNotIn('conda init',' '.join(cmd))
 def test_preview_never_bootstraps_or_contacts_package_channels(self):
  result,row,calls,installed,cert=self.run_loaded_base(apply=False)
  self.assertEqual(result,0);self.assertFalse(any('install' in cmd for cmd,env in calls))
  self.assertEqual(installed['conda']['version'],'24.11.2');self.assertEqual(cert['status'],'planned')
  self.assertEqual(row['conda_bootstrap']['status'],'would-update')
 def test_preview_at_minimum_still_explains_newest_check(self):
  result,row,calls,installed,cert=self.run_loaded_base(apply=False,current=True)
  self.assertEqual(result,0)
  self.assertEqual(row['conda_bootstrap']['status'],'would-check-newest')
  self.assertFalse(any('search' in cmd or 'install' in cmd for cmd,env in calls))
 def test_failed_bootstrap_stops_before_full_base_update(self):
  result,row,calls,installed,cert=self.run_loaded_base(fail_bootstrap=True)
  self.assertEqual(result,2);self.assertEqual(row['status'],'incomplete')
  self.assertFalse(any('--update-all' in cmd for cmd,env in calls))
  self.assertEqual(installed['conda']['version'],'24.11.2');self.assertEqual(cert['status'],'written')
  self.assertEqual(row['conda_bootstrap']['status'],'incomplete')
 def test_current_conda_skips_bootstrap(self):
  result,row,calls,installed,cert=self.run_loaded_base(current=True)
  self.assertEqual(result,0,row['issues'])
  self.assertEqual(len([cmd for cmd,env in calls if 'install' in cmd]),2)
  self.assertEqual(row['conda_bootstrap']['status'],'not-needed')
 def test_success_output_without_new_installed_conda_cannot_continue(self):
  result,row,calls,installed,cert=self.run_loaded_base(stale_bootstrap=True)
  self.assertEqual(result,2);self.assertEqual(row['conda_bootstrap']['status'],'incomplete')
  self.assertFalse(any('--update-all' in cmd for cmd,env in calls))
  self.assertIn('did not meet required minimum',' '.join(row['issues']))
  self.assertIn('in installed: conda=24.11.2',' '.join(row['issues']))
  self.assertEqual(row['conda_bootstrap']['plan_conda_version'],'26.9.4')
  self.assertEqual(row['conda_bootstrap']['installed_conda_version'],'24.11.2')
 def test_stale_plan_explains_no_install_attempted(self):
  result,row,calls,installed,cert=self.run_loaded_base(stale_plan=True)
  self.assertEqual(result,2);self.assertFalse(any('--yes' in cmd for cmd,env in calls))
  self.assertIn('in plan: conda=24.11.2',' '.join(row['issues']))
  self.assertIn('No bootstrap install was attempted',' '.join(row['issues']))
 def test_unexpected_install_dry_run_reports_actual_cause(self):
  result,row,calls,installed,cert=self.run_loaded_base(dry_run_install=True)
  self.assertEqual(result,2);self.assertEqual(installed['conda']['version'],'24.11.2')
  self.assertIn('dry-run result for an install command',' '.join(row['issues']))
  self.assertFalse(any('--update-all' in cmd for cmd,env in calls))
 def test_inherited_dry_run_does_not_negate_apply(self):
  with patch.dict(m.os.environ,{'CONDA_DRY_RUN':'true'}):
   self.assertEqual(m.safe_environment()['CONDA_DRY_RUN'],'false')
 def test_bootstrap_honors_offline_and_channel_guards(self):
  result,row,calls,installed,cert=self.run_loaded_base(offline=True)
  self.assertEqual(result,0,row['issues'])
  for cmd,env in calls:
   if 'search' in cmd:
    self.assertIn('--offline',cmd);self.assertIn('--override-channels',cmd)
    self.assertNotIn('--strict-channel-priority',cmd)
   if 'install' not in cmd:continue
   self.assertIn('--offline',cmd);self.assertEqual(env['CONDA_OFFLINE'],'true')
   self.assertIn('--override-channels',cmd);self.assertIn('--strict-channel-priority',cmd)
   self.assertEqual(env['CONDA_NO_PLUGINS'],'true')
 def test_security_minimum_does_not_skip_newest_conda(self):
  result,row,calls,installed,cert=self.run_loaded_base(current=True,available=['26.9.4','26.11.0','27.0.0rc1'])
  self.assertEqual(result,0,row['issues']);self.assertEqual(installed['conda']['version'],'26.11.0')
  self.assertEqual(row['conda_bootstrap']['latest_available'],'26.11.0')
  solves=[cmd for cmd,env in calls if 'install' in cmd and '--dry-run' in cmd]
  self.assertIn('https://conda.anaconda.org/conda-forge::conda==26.11.0',solves[0])
  self.assertIn('https://conda.anaconda.org/conda-forge::conda>=26.11.0',solves[1])
 def test_full_solve_cannot_undo_latest_bootstrap(self):
  result,row,calls,installed,cert=self.run_loaded_base(available=['26.11.0'],downgrade_full=True)
  self.assertEqual(result,2);self.assertEqual(row['conda_bootstrap']['status'],'updated')
  self.assertEqual(len([cmd for cmd,env in calls if 'install' in cmd and '--yes' in cmd]),1)
 def test_missing_or_stale_available_release_fails_before_install(self):
  for available in ([],['24.11.2'],['27.0.0rc1']):
   with self.subTest(available=available):
    result,row,calls,installed,cert=self.run_loaded_base(available=available,offline=True)
    self.assertEqual(result,2);self.assertFalse(any('install' in cmd for cmd,env in calls))
    self.assertEqual(row['conda_bootstrap']['status'],'incomplete')
 def test_newer_installed_conda_is_retained(self):
  result,row,calls,installed,cert=self.run_loaded_base(current='26.11.0',available=['26.9.4'])
  self.assertEqual(result,0,row['issues']);self.assertEqual(installed['conda']['version'],'26.11.0')
  self.assertEqual(row['conda_bootstrap']['status'],'not-needed')
  solves=[cmd for cmd,env in calls if 'install' in cmd and '--dry-run' in cmd]
  self.assertEqual(len(solves),1);self.assertIn('https://conda.anaconda.org/conda-forge::conda>=26.11.0',solves[0])
 def test_bootstrap_updates_conflicting_manager_stack_together(self):
  result,row,calls,installed,cert=self.run_loaded_base(manager_stack=True)
  self.assertEqual(result,0,row['issues'])
  solve=next(cmd for cmd,env in calls if 'install' in cmd)
  self.assertIn('--update-deps',solve)
  self.assertIn('https://conda.anaconda.org/conda-forge::python',solve)
  for name in ('mamba','libmamba','libmambapy','conda-libmamba-solver'):
   self.assertIn('https://conda.anaconda.org/conda-forge::'+name,solve)
   self.assertIn(name,row['conda_bootstrap']['manager_targets'])
 def test_default_scope_leaves_other_environment_untouched(self):
  result,row,calls,installed,cert=self.run_loaded_base(default_scope=True)
  self.assertEqual(result,0,row['issues']);self.assertFalse(any('env' in cmd and 'list' in cmd for cmd,env in calls))
 def test_all_environments_requires_explicit_scope(self):
  result,row,calls,installed,cert=self.run_loaded_base(all_envs=True,apply=False)
  self.assertEqual(result,0)
 def test_only_does_not_bootstrap_base(self):
  result,row,calls,installed,cert=self.run_loaded_base(only=True,apply=False)
  self.assertEqual(result,0);self.assertNotIn('conda_bootstrap',row)
 def test_scan_requires_explicit_discovery_scope(self):
  with patch.object(m.sys,'argv',['script','--scan-root','/site']),patch('sys.stderr',io.StringIO()):
   with self.assertRaises(SystemExit):m.main()

if __name__=='__main__': unittest.main()
