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

if __name__=='__main__': unittest.main()
