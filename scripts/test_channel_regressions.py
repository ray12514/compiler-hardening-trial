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

class ChannelFlowTests(unittest.TestCase):
 def test_preview_and_apply_with_host_only_record(self):
  for apply in (False,True):
   with self.subTest(apply=apply),tempfile.TemporaryDirectory() as directory:
    p=pathlib.Path(directory);base=p/'mf';(base/'bin').mkdir(parents=True);(base/'bin/conda').touch();(base/'conda-meta').mkdir();(base/'conda-meta/history').touch()
    record={'name':'ca-certificates','version':'2025.1.31','build':'0','channel':'https://conda.anaconda.org'}
    metadata=base/'conda-meta/ca.json';metadata.write_text(json.dumps(record));calls=[]
    def fake(cmd,**kw):
     calls.append(cmd)
     if '--show' in cmd:result={}
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

if __name__=='__main__': unittest.main()
