import contextlib,hashlib,importlib.util,io,json,os,subprocess,tarfile,tempfile,unittest
from pathlib import Path
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('maintenance_promote',Path(__file__).with_name('patch_miniforge_trust.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class PromotionTests(unittest.TestCase):
 def fixture(self,root):
  base=root/'base';(base/'conda-meta').mkdir(parents=True);(base/'bin').mkdir()
  (base/'bin/conda').touch();(base/'bin/python').touch();(base/'bin/python').chmod(0o755);(base/'conda-meta/history').write_text('original history')
  (base/'.condarc').write_text('pinned_packages: [certifi==2024.12.14]\n')
  before={n:{'name':n,'version':v,'build':'0','subdir':'noarch','channel':'conda-forge','sha256':'a'*64,'md5':'b'*32} for n,v in (
   ('conda','24.11.2'),('python','3.12.8'),('conda-libmamba-solver','24.9.0'),('certifi','2024.12.14'),('ca-certificates','2024.12.14'),('pip','24.3.1'),('app','1'),('old-runtime','1'))}
  after={n:dict(r,version={'conda':'26.9.4','python':'3.14.10','conda-libmamba-solver':'26.10.0','certifi':'2026.10.23',
                         'ca-certificates':'2026.10.23','pip':'26.2.2','app':'2'}[n],sha256='c'*64,md5='d'*32)
         for n,r in before.items() if n!='old-runtime'}
  for name in ('curl','libcurl'):after[name]={'name':name,'version':'8.23.0','build':'0','subdir':'noarch','channel':'conda-forge','sha256':'c'*64,'md5':'d'*32}
  def save(prefix,packages):
   (prefix/'conda-meta').mkdir(parents=True,exist_ok=True)
   for p in (prefix/'conda-meta').glob('*.json'):p.unlink()
   for n,r in packages.items():(prefix/'conda-meta'/(n+'.json')).write_text(json.dumps(r))
  save(base,before)
  stage=root/'stage';(stage/'env/conda-meta').mkdir(parents=True);save(stage/'env',after);(stage/'pkgs').mkdir()
  summary={'status':'ready-for-review','source_base':str(base),'source_metadata_unchanged':True,'source_ca_unchanged':True,
           'source_state_after':m.stage_source_state(base),'requested_roots':sorted(after),'conda_update':{'target':'26.9.4','latest_available':'26.9.4'}}
  (stage/'stage-summary.json').write_text(json.dumps(summary));(stage/'candidate-packages.json').write_text(json.dumps(after))
  (stage/'candidate-plan.json').write_text(json.dumps({'success':True,'actions':{'LINK':list(after.values())}}))
  return base,stage,before,after,summary,save

 def test_ready_stage_is_locked_to_its_base_and_candidate_records(self):
  with tempfile.TemporaryDirectory() as directory:
   base,stage,before,after,summary,save=self.fixture(Path(directory))
   approved=m.load_promotion(stage,base)
   self.assertEqual(set(approved['packages']),set(after));self.assertEqual(len(approved['manifest_sha256']),64)
   with self.assertRaisesRegex(RuntimeError,'belongs to'):m.load_promotion(stage,Path(directory)/'another-base')
   (base/'.condarc').write_text('concurrent source change')
   with self.assertRaisesRegex(RuntimeError,'changed since staging'):m.load_promotion(stage,base)

 def test_unready_stage_changed_candidate_missing_hash_or_mismatched_plan_is_rejected(self):
  for case in ('unready','changed-candidate','missing-hash','plan-mismatch'):
   with self.subTest(case=case),tempfile.TemporaryDirectory() as directory:
    base,stage,before,after,summary,save=self.fixture(Path(directory))
    if case=='unready':summary['status']='solve-failed';(stage/'stage-summary.json').write_text(json.dumps(summary))
    elif case=='changed-candidate':after['app']['version']='3';save(stage/'env',after)
    elif case=='missing-hash':after['app'].update(sha256=None,md5=None);(stage/'candidate-packages.json').write_text(json.dumps(after))
    else:(stage/'candidate-plan.json').write_text(json.dumps({'actions':{'LINK':[r for n,r in after.items() if n!='app']}}))
    with self.assertRaises(RuntimeError):m.load_promotion(stage,base)

 def test_permission_block_stops_before_source_writes_and_does_not_relax_reviewed_version(self):
  with tempfile.TemporaryDirectory() as directory:
   base,stage,before,after,summary,save=self.fixture(Path(directory))
   hold={'name':'app','path':str(base/'bin/__pycache__/android_deploy.cpython-312.pyc'),'reason':'parent not writable'}
   with patch.object(m,'permission_holds',return_value={'app':hold}),self.assertRaisesRegex(RuntimeError,'owner/admin access repair'):
    m.load_promotion(stage,base)
   self.assertEqual(m.records(base),before)

 def test_promote_rejects_other_scopes_and_does_not_reuse_global_guard(self):
  for extra in (['--stage','/new'],['--all-envs'],['--only','/other'],['--channel','other'],['--trust-only']):
   with self.subTest(extra=extra),patch.object(m.sys,'argv',['script','--promote','/reviewed']+extra),patch.object(m,'find_base') as find,patch('sys.stderr',io.StringIO()):
    with self.assertRaises(SystemExit):m.main()
    find.assert_not_called()
  with patch.dict(os.environ,{'CSE_CONDA_APPROVED_PLAN':'untrusted'}):self.assertNotIn('CSE_CONDA_APPROVED_PLAN',m.safe_environment())

 def run_promotion(self,apply):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);base,stage,before,after,summary,save=self.fixture(root);installed=dict(before)
   other=base/'envs/untouched';(other/'conda-meta').mkdir(parents=True);(other/'conda-meta/history').write_text('untouched')
   source=root/'site.pem';source.write_text('original PEM');calls=[]
   original={str(p.relative_to(base)):p.read_bytes() for p in base.rglob('*') if p.is_file()}
   def fake(argv,**kwargs):
    argv=list(map(str,argv));calls.append((argv,kwargs.get('env',{})))
    if '-c' in argv and argv[argv.index('-c')+1]==m.AUDIT:
     data={'python':[3,14,10],'packages':{'pip':installed['pip']['version'],'certifi':installed['certifi']['version']},'bundles':{}}
    else:
     values=argv[5:] if '-c' in argv else argv[1:]
     if '__cse_solver_probe__' in values:data={'success':True,'solver':'libmamba'}
     elif '--show' in values:data={'pinned_packages':['certifi==2024.12.14']}
     elif values[:1]==['info']:data={'platform':'linux-64'}
     elif '--explicit' in values:return subprocess.CompletedProcess(argv,0,'@EXPLICIT\n','')
     elif '--dry-run' in values:data={'success':True,'actions':{'LINK':list(after.values()),'UNLINK':list(before.values())}}
     elif values[:1]==['install']:
      installed.clear();installed.update(after);save(base,installed);data={'success':True}
     else:data={'success':True}
    return subprocess.CompletedProcess(argv,0,json.dumps(data),'')
   args=['script',str(base),'--promote',str(stage),'--ca-bundle',str(source),'--log-dir',str(root/'logs')]+(['--apply'] if apply else [])
   with patch.object(m.sys,'argv',args),patch.object(m.os,'geteuid',return_value=123),patch.object(m,'maintenance_gid',return_value=0),patch.object(m,'maintainable',return_value=True),patch.object(m,'filtered_bundle',return_value=('private PEM',[])),patch.object(m,'atomic_write',side_effect=lambda p,data:Path(p).write_text(data)),patch.object(m,'public_permissions',return_value=[]),patch.object(m.subprocess,'run',side_effect=fake),contextlib.redirect_stdout(io.StringIO()):
    result=m.main()
   row=json.loads((root/'logs/summary.json').read_text())[0]
   if not apply:self.assertEqual(original,{str(p.relative_to(base)):p.read_bytes() for p in base.rglob('*') if p.is_file()})
   self.assertEqual((other/'conda-meta/history').read_text(),'untouched');self.assertEqual(source.read_text(),'original PEM')
   self.assertFalse(any('search' in argv for argv,env in calls))
   return result,row,calls,installed

 def test_dry_run_validates_exact_set_with_no_base_or_sibling_changes(self):
  result,row,calls,installed=self.run_promotion(False)
  self.assertEqual(result,0,row['issues']);self.assertEqual(row['status'],'previewed');self.assertEqual(row['promotion']['status'],'validated')
  self.assertFalse(any('--yes' in argv for argv,env in calls));self.assertEqual(installed['conda']['version'],'24.11.2')

 def test_apply_promotes_exact_set_and_removes_unselected_dependency(self):
  result,row,calls,installed=self.run_promotion(True)
  self.assertEqual(result,0,row['issues']);self.assertEqual(row['promotion']['status'],'completed')
  self.assertNotIn('old-runtime',installed);self.assertEqual(installed['conda']['version'],'26.9.4')
  self.assertTrue(all('CSE_CONDA_APPROVED_PLAN' in env for argv,env in calls if 'install' in argv))


class NativePromotionTests(unittest.TestCase):
 @unittest.skipUnless(os.environ.get('CSE_CONDA_PYTHON'),'Set CSE_CONDA_PYTHON for native exact promotion regression')
 def test_native_removal_of_old_explicit_request_and_checksum_guard(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);channel=root/'channel';prefix=root/'prefix';all_records={}
   for subdir in ('linux-64','noarch'):
    folder=channel/subdir;folder.mkdir(parents=True);packages={}
    if subdir=='noarch':
     for name,value in (('cse-keep','1'),('cse-keep','2'),('cse-drop','1')):
      record={'name':name,'version':value,'build':'0','build_number':0,'depends':[],'subdir':'noarch','noarch':'generic'}
      filename=name+'-'+value+'-0.tar.bz2';archive=folder/filename;payload=('version '+value).encode();path='share/'+name
      with tarfile.open(archive,'w:bz2') as tar:
       for member,data in {'info/index.json':json.dumps(record).encode(),'info/files':(path+'\n').encode(),path:payload}.items():
        info=tarfile.TarInfo(member);info.size=len(data);info.mode=0o644;tar.addfile(info,io.BytesIO(data))
      data=archive.read_bytes();record.update(size=len(data),sha256=hashlib.sha256(data).hexdigest(),md5=hashlib.md5(data).hexdigest())
      packages[filename]=record;all_records[(name,value)]=record
    repodata={'info':{'subdir':subdir},'packages':packages,'packages.conda':{},'repodata_version':1}
    for file in ('repodata.json','current_repodata.json'):(folder/file).write_text(json.dumps(repodata))
   env=m.safe_environment();env.update(CONDA_OFFLINE='false',CONDA_REGISTER_ENVS='false',CONDA_PKGS_DIRS=str(root/'pkgs'),CONDA_REPODATA_USE_ZST='false')
   common=['-p',str(prefix),'--solver','libmamba','--json','--yes','--override-channels','--channel',channel.as_uri(),'--strict-channel-priority']
   def run(args,current=env):return subprocess.run([os.environ['CSE_CONDA_PYTHON'],'-I','-B','-c',m.LIBMAMBA_CLI]+args,env=current,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
   created=run(['create']+common+['cse-keep=1','cse-drop=1']);self.assertEqual(created.returncode,0,created.stdout+created.stderr)
   before=m.records(prefix);guard={'prefix':str(prefix),'before':{n:[r['version'],r['build']] for n,r in before.items()},'packages':{'cse-keep':all_records[('cse-keep','2')]}}
   file=root/'approved.json';guard_env=dict(env,CSE_CONDA_APPROVED_PLAN=str(file))
   bad=json.loads(json.dumps(guard));bad['packages']['cse-keep']['sha256']='f'*64;file.write_text(json.dumps(bad))
   rejected=run(['install']+common+['--prune','--no-pin','cse-keep=2'],guard_env)
   self.assertNotEqual(rejected.returncode,0);self.assertIn('reviewed package',rejected.stdout+rejected.stderr)
   self.assertEqual(set(m.records(prefix)),set(before));self.assertEqual((prefix/'share/cse-keep').read_text(),'version 1')
   file.write_text(json.dumps(guard))
   promoted=run(['install']+common+['--prune','--no-pin','cse-keep=2'],guard_env)
   self.assertEqual(promoted.returncode,0,promoted.stdout+promoted.stderr)
   self.assertEqual(set(m.records(prefix)),{'cse-keep'});self.assertEqual((prefix/'share/cse-keep').read_text(),'version 2')


if __name__=='__main__':unittest.main()
