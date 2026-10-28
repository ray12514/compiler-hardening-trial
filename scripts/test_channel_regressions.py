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
 def test_saved_base_update_retains_no_pin_policy(self):
  base=pathlib.Path('/test/base');argv=self.command(base,base)+['--no-pin']
  converted=m.diagnostic_argv(base,base,argv,[])
  self.assertIn('--no-pin',converted);self.assertIn('--dry-run',converted);self.assertNotIn('--yes',converted)
 def test_saved_download_only_is_replayed_as_dry_run(self):
  base=pathlib.Path('/test/base');argv=self.command(base,base)+['--download-only']
  result=m.diagnostic_argv(base,base,argv,[])
  self.assertIn('--dry-run',result);self.assertNotIn('--download-only',result)
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
   self.assertNotIn('Retry with more time',out.getvalue());self.assertIn('explicit pins',out.getvalue());self.assertIn('no conflict conclusion',out.getvalue())

class CachePermissionTests(unittest.TestCase):
 def test_readonly_cache_file_can_be_removed_from_writable_directory(self):
  with tempfile.TemporaryDirectory() as directory:
   parent=pathlib.Path(directory)/'__pycache__';parent.mkdir()
   cache=parent/'android_deploy.cpython-312.pyc';cache.write_bytes(b'cache');cache.chmod(0o444)
   snapshot=m.access_snapshot(cache)
   self.assertTrue(snapshot['parent_directory']['access']['write'])
   cache.unlink()  # Directory entry access matters; file write access is not required.
   self.assertFalse(cache.exists())
 @unittest.skipIf(os.geteuid()==0,'Root can bypass the directory access denial')
 def test_writable_cache_file_does_not_allow_removal_from_readonly_directory(self):
  with tempfile.TemporaryDirectory() as directory:
   parent=pathlib.Path(directory)/'__pycache__';parent.mkdir()
   cache=parent/'android_deploy.cpython-312.pyc';cache.write_bytes(b'cache');parent.chmod(0o555)
   try:
    snapshot=m.access_snapshot(cache)
    self.assertTrue(snapshot['access']['write']);self.assertFalse(snapshot['parent_directory']['access']['write'])
    with self.assertRaises(PermissionError):cache.rename(cache.with_suffix('.pyc.c~'))
    self.assertEqual(cache.read_bytes(),b'cache')
    output=[];m.print_access(snapshot,output.append)
    self.assertTrue(any('Containing directory: '+str(parent) in line for line in output))
   finally:parent.chmod(0o755)
 def test_missing_cache_file_still_reports_parent_and_sticky_mode_without_changes(self):
  with tempfile.TemporaryDirectory() as directory:
   parent=pathlib.Path(directory);parent.chmod(0o1755);cache=parent/'missing.pyc'
   before=parent.stat()
   snapshot=m.access_snapshot(cache)
   self.assertIn('stat_error',snapshot);self.assertTrue(snapshot['parent_directory']['sticky'])
   self.assertEqual(snapshot['parent_directory']['octal'],'1755')
   self.assertEqual(parent.stat().st_mode,before.st_mode);self.assertFalse(cache.exists())
 def test_conda_multierror_tuple_and_rename_permission_paths_are_extracted(self):
  path='/prefix/bin/__pycache__/android_deploy.cpython-312.pyc'
  for error in (f"CondaMultiError: PermissionError(13, 'Permission denied', '{path}')",
                f"PermissionError: [Errno 13] Permission denied: '{path}' -> '{path}.c~'"):
   with self.subTest(error=error):self.assertEqual(m.denied_paths(error),[path])
 def test_bytecode_access_failure_explains_cache_and_directory_without_recommending_bypass(self):
  category,advice=m.failure_category("PermissionError: [Errno 13] Permission denied: '/prefix/bin/__pycache__/android_deploy.cpython-312.pyc'")
  self.assertEqual(category,'Filesystem access');self.assertIn('generated Python bytecode',advice)
  self.assertIn('owner/admin',advice);self.assertIn('non-writable directory',advice)
  self.assertIn('skips alone are nonfatal',advice)

class PermissionHoldTests(unittest.TestCase):
 def fixture(self,root):
  prefix=pathlib.Path(root);(prefix/'bin/__pycache__').mkdir(parents=True)
  source=prefix/'bin/android_deploy.py';source.write_text('print("old")\n')
  cache=prefix/'bin/__pycache__/android_deploy.cpython-312.pyc';cache.write_bytes(b'original cache')
  meta={'qt-tools':{'name':'qt-tools','version':'1','build':'old','files':['bin/android_deploy.py']},
        'python':{'name':'python','version':'3.12.9','build':'0'},
        'certifi':{'name':'certifi','version':'2024.12.14','build':'0'}}
  return prefix,cache,meta
 @unittest.skipIf(os.geteuid()==0,'Root can bypass the directory access denial')
 def test_generated_cache_holds_its_source_package_and_updates_other_security_specs(self):
  with tempfile.TemporaryDirectory() as directory:
   prefix,cache,meta=self.fixture(directory);before=cache.stat();cache.parent.chmod(0o555)
   try:
    holds=m.permission_holds(prefix,meta)
    self.assertEqual(set(holds),{'qt-tools'});self.assertIn('__pycache__',holds['qt-tools']['path'])
    specs,constraint=m.permission_hold_specs(meta,['qt-tools','python','certifi>='+m.MINIMUM['certifi']],holds)
    self.assertIn('qt-tools=1=old',specs);self.assertEqual(constraint,'python=3.12.*')
    self.assertIn('certifi>='+m.MINIMUM['certifi'],specs)
    self.assertEqual(cache.read_bytes(),b'original cache');self.assertEqual(cache.stat().st_ino,before.st_ino)
    self.assertEqual(cache.parent.stat().st_mode&0o777,0o555)
   finally:cache.parent.chmod(0o755)
 def test_readonly_foreign_file_in_writable_directory_is_not_a_hold(self):
  with tempfile.TemporaryDirectory() as directory:
   prefix,cache,meta=self.fixture(directory);cache.chmod(0o444)
   original=pathlib.Path.lstat
   def foreign(path):
    st=original(path)
    if path==cache:
     fields=list(st);fields[4]=os.geteuid()+1;return os.stat_result(fields)
    return st
   with patch.object(pathlib.Path,'lstat',foreign):self.assertEqual(m.permission_holds(prefix,meta),{})
 def test_sticky_foreign_directory_and_file_are_held(self):
  with tempfile.TemporaryDirectory() as directory:
   prefix,cache,meta=self.fixture(directory);cache.parent.chmod(0o1777)
   original=pathlib.Path.lstat
   def foreign(path):
    st=original(path)
    if path in (cache,cache.parent):
     fields=list(st);fields[4]=os.geteuid()+(1 if path==cache else 2);return os.stat_result(fields)
    return st
   # Record only the existing cache for this sticky-bit check.
   meta['qt-tools']['files']=[str(cache.relative_to(prefix))]
   with patch.object(pathlib.Path,'lstat',foreign):
    holds=m.permission_holds(prefix,meta)
   self.assertEqual(set(holds),{'qt-tools'});self.assertIn('Sticky',holds['qt-tools']['reason'])
 def test_redirected_package_parent_is_held_without_touching_external_files(self):
  with tempfile.TemporaryDirectory() as directory:
   root=pathlib.Path(directory);prefix=root/'base';prefix.mkdir();outside=root/'outside';outside.mkdir()
   (outside/'file').write_text('external');(prefix/'share').symlink_to(outside,target_is_directory=True)
   holds=m.permission_holds(prefix,{'app':{'version':'1','build':'0','files':['share/file']}})
   self.assertIn('app',holds);self.assertIn('symlink',holds['app']['reason'])
   self.assertEqual((outside/'file').read_text(),'external')
 def test_unowned_cache_name_alone_does_not_identify_a_package(self):
  with tempfile.TemporaryDirectory() as directory:
   prefix,cache,meta=self.fixture(directory);meta['qt-tools']['files']=[]
   self.assertEqual(m.permission_holds(prefix,meta),{})
 def test_security_minimum_or_newest_conda_cannot_be_relaxed_for_a_hold(self):
  for name,current,minimum in (('certifi','2024.12.14',m.MINIMUM['certifi']),('conda','26.9.4','26.10.0')):
   hold={'name':name,'version':current,'build':'0','path':'/blocked/cache.pyc','reason':'denied','python_files':True}
   with self.subTest(name=name),self.assertRaisesRegex(RuntimeError,'Permission-held package '+name):
    m.permission_hold_specs({name:hold},[name+'>='+minimum],{name:hold},minimum)
 def test_held_dependency_is_retained_and_blocked_boost_migration_is_deferred(self):
  meta={'app':{'depends':['dep']},'dep':{},'boost':{'channel':'conda-forge'}}
  intent=m.base_package_intent(meta,ignore_pins=True,held={'dep','boost'})
  self.assertIn('dep',intent['roots']);self.assertIn('boost',intent['roots'])
  self.assertNotIn('libboost-python-devel',intent['roots']);self.assertEqual(intent['replacements'],[])
 def test_same_build_relink_or_removal_of_held_package_is_rejected(self):
  for action in ('LINK','UNLINK'):
   with self.subTest(action=action),self.assertRaisesRegex(RuntimeError,'permission-held'):
    m.verify_permission_holds({'actions':{action:[{'name':'qt-tools','version':'1','build':'old'}]}},{'qt-tools':{}})
  m.verify_permission_holds({'actions':{'LINK':[{'name':'conda'}]}},{'qt-tools':{}})
 def test_manifest_paths_cannot_leave_prefix(self):
  for path in ('../outside/file','/outside/file','share/../../outside/file','share\\outside'):
   with self.subTest(path=path),self.assertRaisesRegex(RuntimeError,'Unsafe installed package path'):
    list(m.package_paths({'files':[path]}))
 def test_inherited_transaction_guards_are_not_trusted(self):
  with patch.dict(os.environ,{'CSE_CONDA_PERMISSION_HOLDS':'untrusted'}):
   self.assertNotIn('CSE_CONDA_PERMISSION_HOLDS',m.safe_environment())
 @unittest.skipIf(os.geteuid()==0,'Root can bypass the directory access denial')
 def test_access_repair_releases_the_temporary_hold_on_the_next_check(self):
  with tempfile.TemporaryDirectory() as directory:
   prefix,cache,meta=self.fixture(directory);cache.parent.chmod(0o555)
   try:self.assertEqual(set(m.permission_holds(prefix,meta)),{'qt-tools'})
   finally:cache.parent.chmod(0o755)
   self.assertEqual(m.permission_holds(prefix,meta),{});self.assertEqual(cache.read_bytes(),b'original cache')
 def test_saved_success_report_lists_holds_without_calling_them_failed_updates(self):
  with tempfile.TemporaryDirectory() as directory:
   root=pathlib.Path(directory)
   row={'prefix':'/site/base','status':'updated-with-skips','issues':[],
        'permission_holds':[{'name':'qt-tools','version':'1','build':'old','path':'/site/base/bin/__pycache__/android_deploy.cpython-312.pyc','reason':'Directory denied'}]}
   (root/'summary.json').write_text(json.dumps([row]))
   with patch('sys.stdout',io.StringIO()) as output,patch.object(m.subprocess,'run') as run:
    self.assertEqual(m.report_existing(root),0)
   run.assert_not_called();self.assertIn('Deferred package: qt-tools=1=old',output.getvalue())
   self.assertIn('Failure/review categories: none',output.getvalue())

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
 @unittest.skipUnless(os.environ.get('CSE_CONDA_PYTHON'),'Set CSE_CONDA_PYTHON to test real native pruning')
 def test_real_install_path_prunes_retired_names_in_the_same_solve(self):
  with tempfile.TemporaryDirectory() as directory:
   root=pathlib.Path(directory);prefix=root/'prefix';(prefix/'conda-meta').mkdir(parents=True)
   (prefix/'conda-meta/history').write_text('')
   channel=root/'channel'
   def record(name,version,depends=(),constrains=()):
    return {'name':name,'version':version,'build':'0','build_number':0,'depends':list(depends),
            'constrains':list(constrains),'subdir':'noarch','channel':channel.as_uri(),'size':1,
            'md5':'0'*32,'sha256':'0'*64,'noarch':'generic'}
   installed=[record('app','1',['boost']),record('boost','1',['boost-cpp']),record('boost-cpp','1'),
              record('libboost-python-devel','1',['libboost-devel']),record('libboost-devel','1')]
   for r in installed:(prefix/'conda-meta'/(r['name']+'-'+r['version']+'-0.json')).write_text(json.dumps(r))
   packages=[record('app','2',['libboost-python-devel']),
             record('libboost-python-devel','2',['libboost-devel'],['boost <0.0a0']),
             record('libboost-devel','2',[],['boost-cpp <0.0a0']),
             record('libboost-python-devel','1',['libboost-devel']),record('libboost-devel','1')]
   for subdir in ('linux-64','noarch'):
    (channel/subdir).mkdir(parents=True)
    data={'info':{'subdir':subdir},'packages':{},'packages.conda':{},'repodata_version':1}
    if subdir=='noarch':data['packages']={r['name']+'-'+r['version']+'-0.tar.bz2':r for r in packages}
    for name in ('repodata.json','current_repodata.json'):(channel/subdir/name).write_text(json.dumps(data))
   env=m.safe_environment();env.update(CONDA_OFFLINE='false',CONDA_REGISTER_ENVS='false',
    CONDA_PKGS_DIRS=str(root/'cache'),CONDA_ENVS_PATH=str(root/'envs'),CONDA_REPODATA_USE_ZST='false')
   argv=['install','-p',str(prefix),'--solver','libmamba','--json','--dry-run','--update-all','--prune',
         '--override-channels','--channel',channel.as_uri(),'--strict-channel-priority',
         'app','libboost-python-devel','libboost-devel']
   result=subprocess.run([os.environ['CSE_CONDA_PYTHON'],'-I','-B','-c',m.LIBMAMBA_CLI]+argv,
                         env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
   self.assertEqual(result.returncode,0,result.stdout+result.stderr)
   plan=json.loads(result.stdout);actions=plan['actions']
   linked={r['name'] for r in actions['LINK']};unlinked={r['name'] for r in actions['UNLINK']}
   self.assertEqual(unlinked-linked,{'boost','boost-cpp'})
   self.assertEqual(linked,{'app','libboost-python-devel','libboost-devel'})
   self.assertTrue(all(r['version']=='2' for r in actions['LINK']))
   self.assertEqual(len(list((prefix/'conda-meta').glob('*.json'))),len(installed))

class PermissionHoldRuntimeTests(unittest.TestCase):
 @unittest.skipUnless(os.environ.get('CSE_CONDA_PYTHON'),'Set CSE_CONDA_PYTHON for native blocked-file transaction regression')
 @unittest.skipIf(os.geteuid()==0,'Root can bypass the directory access denial')
 def test_native_update_preserves_blocked_package_and_updates_free_package(self):
  import hashlib,tarfile
  with tempfile.TemporaryDirectory() as directory:
   root=pathlib.Path(directory);channel=root/'channel';prefix=root/'prefix'
   cache_path='bin/__pycache__/android_deploy.cpython-312.pyc';free_path='share/free-app.txt'
   for subdir in ('linux-64','noarch'):
    folder=channel/subdir;folder.mkdir(parents=True);packages={}
    if subdir=='noarch':
     for name,path in (('cse-held-app',cache_path),('cse-free-app',free_path)):
      for value in ('1','2','3'):
       record={'name':name,'version':value,'build':'0','build_number':0,
               'depends':['cse-held-app >=2'] if name=='cse-free-app' and value=='3' else [],'subdir':'noarch','noarch':'generic'}
       filename=name+'-'+value+'-0.tar.bz2';archive=folder/filename;content=(name+' version '+value+'\n').encode()
       files={'info/index.json':json.dumps(record).encode(),'info/files':(path+'\n').encode(),path:content}
       with tarfile.open(archive,'w:bz2') as tar:
        for member,data in files.items():
         info=tarfile.TarInfo(member);info.size=len(data);info.mode=0o644;tar.addfile(info,io.BytesIO(data))
       payload=archive.read_bytes();packages[filename]=dict(record,size=len(payload),md5=hashlib.md5(payload).hexdigest(),sha256=hashlib.sha256(payload).hexdigest())
    data={'info':{'subdir':subdir},'packages':packages,'packages.conda':{},'repodata_version':1}
    for name in ('repodata.json','current_repodata.json'):(folder/name).write_text(json.dumps(data))
   env=m.safe_environment();env.update(CONDA_OFFLINE='false',CONDA_REGISTER_ENVS='false',
    CONDA_PKGS_DIRS=str(root/'cache'),CONDA_ENVS_PATH=str(root/'envs'),CONDA_REPODATA_USE_ZST='false')
   common=['-p',str(prefix),'--solver','libmamba','--json','--yes','--override-channels',
           '--channel',channel.as_uri(),'--strict-channel-priority']
   def run(command,guard=False):
    current=dict(env)
    if guard:current['CSE_CONDA_PERMISSION_HOLDS']=json.dumps({'prefix':str(prefix),'packages':['cse-held-app']})
    return subprocess.run([os.environ['CSE_CONDA_PYTHON'],'-I','-B','-c',m.LIBMAMBA_CLI]+command,
                          env=current,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
   created=run(['create']+common+['cse-held-app=1','cse-free-app=1'])
   self.assertEqual(created.returncode,0,created.stdout+created.stderr)
   cache=prefix/cache_path;before=cache.stat();original=cache.read_bytes();cache.parent.chmod(0o555)
   try:
    denied=run(['install']+common+['cse-held-app=2','cse-free-app=2'])
    self.assertNotEqual(denied.returncode,0);self.assertIn('Permission',denied.stdout+denied.stderr)
    self.assertEqual(m.records(prefix)['cse-held-app']['version'],'1');self.assertEqual(cache.read_bytes(),original)
    holds=m.permission_holds(prefix,m.records(prefix));self.assertEqual(set(holds),{'cse-held-app'})
    refused=run(['install']+common+['cse-held-app=2','cse-free-app=2'],guard=True)
    self.assertNotEqual(refused.returncode,0);self.assertIn('permission-held',refused.stdout+refused.stderr)
    same_build=run(['install']+common+['--force-reinstall','cse-held-app=1'],guard=True)
    self.assertNotEqual(same_build.returncode,0);self.assertIn('permission-held',same_build.stdout+same_build.stderr)
    specs,_=m.permission_hold_specs(m.records(prefix),['cse-held-app','cse-free-app=2'],holds)
    planned=run(['install']+common+['--update-all','--prune','--no-pin','--dry-run']+specs,guard=True)
    self.assertEqual(planned.returncode,0,planned.stdout+planned.stderr)
    plan=json.loads(planned.stdout);m.verify_permission_holds(plan,holds)
    final,exact=m.exact_plan_specs(m.records(prefix),plan,{'cse-held-app':channel.as_uri()},[channel.as_uri()],{})
    updated=run(['install']+common+['--prune','--no-pin']+exact,guard=True)
    self.assertEqual(updated.returncode,0,updated.stdout+updated.stderr)
    installed=m.records(prefix)
    self.assertEqual(installed['cse-held-app']['version'],'1');self.assertEqual(installed['cse-free-app']['version'],'2')
    self.assertEqual(cache.read_bytes(),original);self.assertEqual(cache.stat().st_ino,before.st_ino)
    self.assertEqual((cache.stat().st_uid,cache.stat().st_gid,cache.stat().st_mode),(before.st_uid,before.st_gid,before.st_mode))
    self.assertEqual(cache.parent.stat().st_mode&0o777,0o555)
    incompatible=run(['install']+common+['cse-held-app=1','cse-free-app=3'],guard=True)
    self.assertNotEqual(incompatible.returncode,0);self.assertIn('Unsatisfiable',incompatible.stdout+incompatible.stderr)
    self.assertEqual(m.records(prefix)['cse-free-app']['version'],'2');self.assertEqual(cache.read_bytes(),original)
   finally:cache.parent.chmod(0o755)

class BasePinRuntimeTests(unittest.TestCase):
 @unittest.skipUnless(os.environ.get('CSE_CONDA_PYTHON'),'Set CSE_CONDA_PYTHON for native pin regression')
 def test_native_no_pin_allows_security_and_application_updates_from_every_pin_source(self):
  with tempfile.TemporaryDirectory() as directory:
   root=pathlib.Path(directory);prefix=root/'prefix';(prefix/'conda-meta').mkdir(parents=True)
   (prefix/'conda-meta/history').write_text('');channel=root/'channel'
   def record(name,value):return {'name':name,'version':value,'build':'0','build_number':0,'depends':[],
    'subdir':'noarch','channel':channel.as_uri(),'size':1,'md5':'0'*32,'sha256':'0'*64,'noarch':'generic'}
   for r in (record('certifi','2024.12.14'),record('numpy','1.26.4')):
    (prefix/'conda-meta'/(r['name']+'-'+r['version']+'-0.json')).write_text(json.dumps(r))
   for subdir in ('linux-64','noarch'):
    (channel/subdir).mkdir(parents=True);packages={}
    if subdir=='noarch':
     for r in (record('certifi','2026.10.23'),record('numpy','1.26.4'),record('numpy','2.0')):
      packages[r['name']+'-'+r['version']+'-0.tar.bz2']=r
    data={'info':{'subdir':subdir},'packages':packages,'packages.conda':{},'repodata_version':1}
    for filename in ('repodata.json','current_repodata.json'):(channel/subdir/filename).write_text(json.dumps(data))
   argv=['install','-p',str(prefix),'--solver','libmamba','--json','--dry-run','--update-all','--prune',
         '--override-channels','--channel',channel.as_uri(),'--strict-channel-priority','certifi>=2026.10.19','numpy']
   for source in ('prefix','config','environment'):
    with self.subTest(source=source):
     pinfile=prefix/'conda-meta/pinned';config=root/'condarc'
     for p in (pinfile,config):
      if p.exists():p.unlink()
     env=m.safe_environment();env.update(CONDA_OFFLINE='false',CONDA_REGISTER_ENVS='false',CONDA_PKGS_DIRS=str(root/'cache'),CONDA_REPODATA_USE_ZST='false')
     pins=['certifi==2024.12.14','numpy==1.26.4']
     if source=='prefix':pinfile.write_text('\n'.join(pins)+'\n')
     elif source=='config':config.write_text('pinned_packages:\n'+''.join('  - '+p+'\n' for p in pins));env['CONDARC']=str(config)
     else:env['CONDA_PINNED_PACKAGES']='&'.join(pins)
     before={str(p):p.read_bytes() for p in (pinfile,config) if p.exists()}
     def solve(ignore):
      return subprocess.run([os.environ['CSE_CONDA_PYTHON'],'-I','-B','-c',m.LIBMAMBA_CLI]+argv+(['--no-pin'] if ignore else []),
                            env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
     rejected=solve(False);self.assertNotEqual(rejected.returncode,0);self.assertIn('SpecsConfigurationConflict',rejected.stdout)
     accepted=solve(True);self.assertEqual(accepted.returncode,0,accepted.stdout+accepted.stderr)
     links=json.loads(accepted.stdout)['actions']['LINK']
     self.assertEqual({r['name']:r['version'] for r in links},{'certifi':'2026.10.23','numpy':'2.0'})
     self.assertEqual(before,{str(p):p.read_bytes() for p in (pinfile,config) if p.exists()})

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

class XkbMigrationTests(unittest.TestCase):
 def fixture(self,directory):
  prefix=pathlib.Path(directory)/'base';(prefix/'etc/cse-trust').mkdir(parents=True)
  source=prefix/m.XKB_PATH;(source/'geometry').mkdir(parents=True)
  (source/'geometry/hp').write_text('original keyboard map');(source/'geometry/hp').chmod(0o640)
  meta={'xkeyboard-config':{'name':'xkeyboard-config','version':'2.42','build':'old','files':[m.XKB_PATH+'/geometry/hp']}}
  (prefix/'conda-meta').mkdir();(prefix/'conda-meta/xkeyboard-config.json').write_text(json.dumps(meta['xkeyboard-config']))
  return prefix,source,meta
 def preserve(self,prefix,meta,migration):
  with patch.object(m,'maintenance_gid',return_value=os.getegid()):m.preserve_xkb_tree(prefix,meta,migration)
 def test_success_preserves_original_data_and_private_backup_permissions(self):
  with tempfile.TemporaryDirectory() as directory:
   prefix,source,meta=self.fixture(directory);original=(source/'geometry/hp').stat();migration={}
   self.preserve(prefix,meta,migration);backup=pathlib.Path(migration['backup'])
   self.assertFalse(source.exists());self.assertEqual((backup/'geometry/hp').read_text(),'original keyboard map')
   actual=(backup/'geometry/hp').stat();self.assertEqual((actual.st_ino,actual.st_uid,actual.st_gid,actual.st_mode),(original.st_ino,original.st_uid,original.st_gid,original.st_mode))
   self.assertEqual(backup.parent.stat().st_mode&0o777,0o700)
   self.assertEqual(pathlib.Path(migration['manifest']).stat().st_mode&0o777,0o600)
   target=prefix/'share/xkeyboard-config-2';(target/'geometry').mkdir(parents=True);(target/'geometry/hp').write_text('new keyboard map')
   source.symlink_to(m.XKB_LINK);m.verify_xkb_tree(prefix,migration)
   self.assertEqual(migration['status'],'installed-original-preserved')
   with patch.object(m,'maintenance_gid',return_value=os.getegid()):m.public_permissions(prefix,prefix,True,lambda line:None,excludes=[prefix/m.PATH_BACKUPS])
   self.assertEqual((backup/'geometry/hp').stat().st_mode,original.st_mode)
   self.assertEqual(backup.parent.stat().st_mode&0o777,0o700)
 def test_rollback_restores_original_directory_after_failed_install(self):
  with tempfile.TemporaryDirectory() as directory:
   prefix,source,meta=self.fixture(directory);migration={};self.preserve(prefix,meta,migration)
   target=prefix/'share/xkeyboard-config-2';target.mkdir();source.symlink_to(m.XKB_LINK)
   m.restore_xkb_tree(prefix,meta,migration)
   self.assertEqual(migration['status'],'restored-after-failure');self.assertFalse(source.is_symlink())
   self.assertEqual((source/'geometry/hp').read_text(),'original keyboard map');self.assertFalse(pathlib.Path(migration['backup']).exists())
 def test_partial_package_rollback_keeps_backup_and_active_path_for_recovery(self):
  with tempfile.TemporaryDirectory() as directory:
   prefix,source,meta=self.fixture(directory);migration={};self.preserve(prefix,meta,migration)
   current=dict(meta['xkeyboard-config'],version='2.48');(prefix/'conda-meta/xkeyboard-config.json').write_text(json.dumps(current))
   source.symlink_to(m.XKB_LINK);m.restore_xkb_tree(prefix,meta,migration)
   self.assertEqual(migration['status'],'recovery-needed');self.assertTrue(source.is_symlink());self.assertTrue(pathlib.Path(migration['backup']).is_dir())
 def test_custom_and_other_package_files_are_left_untouched(self):
  for mode in ('custom','shared'):
   with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory:
    prefix,source,meta=self.fixture(directory)
    if mode=='custom':(source/'custom-map').write_text('custom data')
    else:meta['other']={'files':[m.XKB_PATH+'/geometry/hp']}
    with self.assertRaisesRegex(RuntimeError,'untracked or other-package'):self.preserve(prefix,meta,{})
    self.assertTrue(source.is_dir());self.assertFalse((prefix/m.PATH_BACKUPS).exists())
 def test_symlink_parent_cannot_redirect_migration_outside_prefix(self):
  with tempfile.TemporaryDirectory() as directory:
   root=pathlib.Path(directory);prefix=root/'base';prefix.mkdir();outside=root/'outside';(outside/'X11/xkb').mkdir(parents=True)
   (outside/'X11/xkb/map').write_text('outside data');(prefix/'share').symlink_to(outside)
   with self.assertRaisesRegex(RuntimeError,'symlink parent'):m.inspect_xkb_tree(prefix,{})
   self.assertEqual((outside/'X11/xkb/map').read_text(),'outside data')
 def test_replacement_data_symlink_cannot_redirect_installation(self):
  with tempfile.TemporaryDirectory() as directory:
   prefix,source,meta=self.fixture(directory);outside=pathlib.Path(directory)/'outside';outside.mkdir()
   (prefix/'share/xkeyboard-config-2').symlink_to(outside)
   with self.assertRaisesRegex(RuntimeError,'replacement data path'):self.preserve(prefix,meta,{})
   self.assertEqual((source/'geometry/hp').read_text(),'original keyboard map');self.assertEqual(list(outside.iterdir()),[])
 def test_collision_has_filesystem_category(self):
  category,advice=m.failure_category("CondaMultiError: FileExistsError(17, 'File exists', '../xkeyboard-config-2', '/base/share/X11/xkb')")
  self.assertEqual(category,'Package file collision');self.assertIn('manifest',advice)

class BaseUpdatePolicyTests(unittest.TestCase):
 def test_base_can_ignore_all_pins_without_retaining_old_dependency_or_boost_names(self):
  meta={'app':{'depends':['dependency']},'dependency':{},'boost':{'channel':'conda-forge'}}
  with tempfile.TemporaryDirectory() as directory:
   p=pathlib.Path(directory);(p/'conda-meta').mkdir();(p/'conda-meta/pinned').write_text('dependency==1\nboost==1.82\n')
   intent=m.base_package_intent(meta,p,{'pinned_packages':['certifi==2024.12.14']},ignore_pins=True)
   self.assertEqual(set(intent['roots']),{'app','libboost-python-devel'})
   self.assertEqual(intent['pinned_packages'],[])
   self.assertEqual(set(intent['ignored_pins']),{'dependency==1','boost==1.82','certifi==2024.12.14'})
 def test_dependency_graph_preserves_applications_without_forcing_old_dependencies(self):
  meta={n:{'version':'1','build':'0','depends':deps} for n,deps in {
   'conda':['python','old-solver-runtime'],'python':['libffi'],'jupyter':['jupyter_core','python'],
   'jupyter_core':['python'],'numpy':['python','old-blas'],'old-blas':[],'libffi':[],
   'old-solver-runtime':[],'standalone-tool':[]}.items()}
  intent=m.base_package_intent(meta)
  self.assertEqual(set(intent['roots']),{'conda','python','jupyter','numpy','standalone-tool'})
  targets,allowed,specs=m.plan_specs(meta,False,broad=True)
  self.assertNotIn('old-blas',specs);self.assertNotIn('old-solver-runtime',specs)
 def test_dependency_cycles_and_isolated_packages_are_retained(self):
  meta={n:{'depends':deps} for n,deps in {'a':['b'],'b':['a','child'],'child':[],'isolated':[]}.items()}
  self.assertEqual(set(m.base_package_intent(meta)['roots']),{'a','b','isolated'})
 def test_history_keeps_explicit_dependency_requests_and_ignores_full_snapshots(self):
  meta={'app':{'depends':['dep']},'dep':{'depends':[]}}
  with tempfile.TemporaryDirectory() as directory:
   p=pathlib.Path(directory);(p/'conda-meta').mkdir()
   history=p/'conda-meta/history'
   snapshot="==> 2024-01-01 <==\n+conda-forge::app-1-0\n+conda-forge::dep-1-0\n# update specs: ['app=1=0', 'dep=1=0']\n"
   history.write_text(snapshot)
   self.assertEqual(m.base_package_intent(meta,p)['roots'],['app'])
   history.write_text(snapshot+"==> 2024-02-01 <==\n# update specs: ['dep>=1']\n")
   self.assertEqual(m.base_package_intent(meta,p)['roots'],['app','dep'])
   history.write_text(history.read_text()+"==> 2024-03-01 <==\n# remove specs: ['dep']\n")
   self.assertEqual(m.base_package_intent(meta,p)['roots'],['app'])
 def test_explicit_pins_protect_dependencies_from_pruning(self):
  meta={'app':{'depends':['dep','other']},'dep':{},'other':{}}
  with tempfile.TemporaryDirectory() as directory:
   p=pathlib.Path(directory);(p/'conda-meta').mkdir();(p/'conda-meta/pinned').write_text('dep==1 # site pin\n')
   self.assertEqual(set(m.base_package_intent(meta,p,{'pinned_packages':['other=2']})['roots']),set(meta))
 def test_boost_migration_preserves_development_functionality_and_respects_pins(self):
  meta={n:{'channel':'conda-forge','depends':[]} for n in ('boost','boost-cpp')}
  intent=m.base_package_intent(meta)
  self.assertEqual(set(intent['roots']),{'libboost-python-devel','libboost-devel'})
  self.assertEqual({r['name'] for r in intent['replacements']},set(meta))
  self.assertIn('boost',m.base_package_intent(meta,config={'pinned_packages':['boost==1.82']})['roots'])
  meta['boost']['channel']='other-channel'
  self.assertIn('boost',m.base_package_intent(meta)['roots'])
 def test_pruned_dependency_is_removed_from_exact_execution_specs(self):
  meta={'app':{'version':'1','build':'old'},'dep':{'version':'1','build':'0'}}
  plan={'actions':{'UNLINK':[dict(name=n,**r) for n,r in meta.items()],
                   'LINK':[{'name':'app','version':'2','build':'new','channel':'conda-forge'}]}}
  self.assertEqual(m.check_plan(plan,None,{'app'}),['app','dep'])
  final,exact=m.exact_plan_specs(meta,plan,{},[],{})
  self.assertEqual(final,{'app':('2','new')});self.assertFalse(any('dep=' in spec for spec in exact))
  with self.assertRaisesRegex(RuntimeError,'removal'):m.check_plan(plan,None,{'dep'})
  with self.assertRaisesRegex(RuntimeError,'differ'):m.verify_installed_plan(final,dict(meta,app={'version':'2','build':'new'}))
 def test_exact_plan_uses_actual_base_url_instead_of_a_canonical_site_channel_label(self):
  for source in ('file:///opt/site/channel','https://mirror.example/site/science'):
   with self.subTest(source=source):
    plan={'actions':{'LINK':[{'name':'app','version':'2','build_string':'0','channel':'science','base_url':source}]}}
    final,exact=m.exact_plan_specs({},plan,{},[source],{})
    self.assertEqual(final,{'app':('2','0')});self.assertEqual(exact,[source+'::app=2=0'])
 def test_missing_retained_application_is_rejected(self):
  with self.assertRaisesRegex(RuntimeError,'jupyter'):m.verify_retained({'conda':('26.9.4','0')},{'conda','jupyter'})
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
                     manager_stack=False,dry_run_install=False,missing_solver=False,prune_dependency=False,stale_removal=False,configured_pins=(),xkb_layout=False,xkb_uncached=False,
                     blocked_package=False,touch_hold=False):
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
   if prune_dependency:
    installed['legacy-runtime']={'name':'legacy-runtime','version':'1','build':'0','channel':'conda-forge'}
    installed['numpy']['depends']=['legacy-runtime']
   if blocked_package:
    name='certifi' if blocked_package=='security' else 'qt-tools'
    if name not in installed:installed[name]={'name':name,'version':'1','build':'old','channel':'conda-forge'};updates[name]='2'
    installed[name]['files']=['bin/android_deploy.py'];(base/'bin/android_deploy.py').write_text('original tool')
    cache=base/'bin/__pycache__/android_deploy.cpython-312.pyc';cache.parent.mkdir();cache.write_bytes(b'original cache');cache.parent.chmod(0o555)
   if xkb_layout:
    installed['xkeyboard-config']={'name':'xkeyboard-config','version':'2.42','build':'0','channel':'conda-forge','files':[m.XKB_PATH+'/geometry/hp']};updates['xkeyboard-config']='2.48'
    source=base/m.XKB_PATH;(source/'geometry').mkdir(parents=True);(source/'geometry/hp').write_text('original map')
    if xkb_layout=='custom':(source/'custom-map').write_text('custom map')
   def save():
    for path in (base/'conda-meta').glob('*.json'):path.unlink()
    for name,record in installed.items():(base/'conda-meta'/(name+'.json')).write_text(json.dumps(record))
   save();calls=[];cache_ready=not xkb_uncached
   def fake(cmd,**kwargs):
    nonlocal cache_ready
    cmd=list(map(str,cmd));calls.append((cmd,dict(kwargs.get('env',{}))))
    if cmd[1:]==['info','--base']:return subprocess.CompletedProcess(cmd,0,str(base)+'\n','')
    if '__cse_solver_probe__' in cmd:output={'success':True,'solver':'classic' if missing_solver else 'libmamba'}
    elif '--show' in cmd:output={'pinned_packages':list(configured_pins)}
    elif 'search' in cmd:output={'conda':[{'name':'conda','version':v,'channel':'conda-forge','build':'0'} for v in available]}
    elif '--explicit' in cmd:return subprocess.CompletedProcess(cmd,0,'@EXPLICIT\n','')
    elif m.XKB_CACHE_PROBE in cmd:output={'available':cache_ready,'target':m.XKB_LINK}
    elif 'install' in cmd:
     if '--download-only' in cmd:
      self.assertEqual(installed['xkeyboard-config']['version'],'2.42');self.assertEqual((base/m.XKB_PATH/'geometry/hp').read_text(),'original map')
      cache_ready=True
      return subprocess.CompletedProcess(cmd,0,'',json.dumps({'exception_name':'CondaExitZero','message':'Package caches prepared; transaction cancelled'}))
     elif '--dry-run' in cmd:
      held=set(json.loads(kwargs['env'].get('CSE_CONDA_PERMISSION_HOLDS','{}')).get('packages',()))
      if held and 'python' in updates:updates['python']='3.12.10'
      links=[dict(installed[n],version=v) for n,v in updates.items() if n not in held or touch_hold]
      if stale_plan:links[0]['version']=installed['conda']['version']
      output={'success':True,'actions':{'LINK':links}}
      if prune_dependency:output['actions']['UNLINK']=[dict(installed['legacy-runtime'])]
     else:
      if dry_run_install:return subprocess.CompletedProcess(cmd,0,json.dumps({'success':True,'dry_run':True}),'')
      if fail_install:return subprocess.CompletedProcess(cmd,1,'','Package installation failed')
      if not stale_install:
       held=set(json.loads(kwargs['env'].get('CSE_CONDA_PERMISSION_HOLDS','{}')).get('packages',()))
       for name,value in updates.items():
        if name not in held:installed[name]['version']=value
      if prune_dependency and not stale_removal:installed.pop('legacy-runtime')
      if xkb_layout:
       new=base/'share/xkeyboard-config-2/geometry';new.mkdir(parents=True);(new/'hp').write_text('new map');(base/m.XKB_PATH).symlink_to(m.XKB_LINK)
      save();output={'success':True}
    elif '-c' in cmd:output={'python':[3,14,0],'packages':{},'bundles':{}}
    else:output={'success':True}
    return subprocess.CompletedProcess(cmd,0,json.dumps(output),'')
   scope=[] if default_scope else ['--all-envs'] if all_envs else ['--only',str(other)] if only else ['--base-only']
   argv=['patch_miniforge_trust.py']+scope+['--log-dir',str(root/'logs')]+(['--apply'] if apply else [])+(['--offline'] if offline else [])
   with patch.object(m.sys,'argv',argv),patch.dict(m.os.environ,{'CONDA_EXE':str(base/'bin/conda')}),patch.object(m.os,'geteuid',return_value=123),patch.object(m,'maintenance_gid',return_value=0),patch.object(m,'maintainable',return_value=True),patch.object(m,'choose_source',return_value=root/'source.pem'),patch.object(m,'filtered_bundle',return_value=('PEM',[])),patch.object(m,'atomic_write',side_effect=lambda path,data:pathlib.Path(path).write_text(data)),patch.object(m.subprocess,'run',side_effect=fake),patch.object(m,'public_permissions',return_value=[]),patch('sys.stdout',io.StringIO()):result=m.main()
   rows=json.loads((root/'logs/summary.json').read_text())
   if blocked_package:
    self.assertEqual(cache.read_bytes(),b'original cache');self.assertEqual(cache.parent.stat().st_mode&0o777,0o555)
    cache.parent.chmod(0o755)
   if xkb_layout and apply:
    migration=rows[0].get('xkb_migration')
    if result==0:
     self.assertEqual((pathlib.Path(migration['backup'])/'geometry/hp').read_text(),'original map')
     self.assertEqual((base/m.XKB_PATH/'geometry/hp').read_text(),'new map')
    else:self.assertEqual((base/m.XKB_PATH/'geometry/hp').read_text(),'original map')
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
  self.assertTrue(all('--no-pin' in cmd for cmd in installs))
  self.assertIn('libmamba',installs[0]);self.assertNotIn('--update-deps',installs[0])
  for name in ('python','jupyter_core','libboost-python','mamba'):
   self.assertIn(name,installs[0]);self.assertFalse(any('::'+name in value for value in installs[0]))
  self.assertEqual(installed['conda']['version'],'26.9.4');self.assertEqual(installed['numpy']['version'],'2.0')
  self.assertEqual(row['conda_update']['status'],'updated');self.assertNotIn('conda_bootstrap',row)
 def test_blocked_package_is_deferred_while_conda_certifi_and_other_packages_update(self):
  result,row,calls,installed=self.run_loaded_base(manager_stack=True,blocked_package=True)
  self.assertEqual(result,0,row['issues']);self.assertEqual(row['status'],'updated-with-skips')
  self.assertEqual([h['name'] for h in row['permission_holds']],['qt-tools'])
  self.assertEqual(installed['qt-tools']['version'],'1');self.assertEqual(installed['conda']['version'],'26.9.4')
  self.assertEqual(installed['certifi']['version'],m.MINIMUM['certifi']);self.assertEqual(installed['numpy']['version'],'2.0')
  self.assertEqual(row['permission_python_constraint'],'python=3.12.*')
  self.assertTrue(all('qt-tools=1=old' in c for c,e in calls if 'install' in c and '--dry-run' in c))
 def test_blocked_outdated_security_package_stops_before_any_install(self):
  result,row,calls,installed=self.run_loaded_base(manager_stack=True,blocked_package='security')
  self.assertEqual(result,2);self.assertEqual(row['status'],'incomplete')
  self.assertIn('Permission-held package certifi',' '.join(row['issues']));self.assertFalse(any('install' in c for c,e in calls))
 def test_a_solver_plan_touching_a_hold_stops_before_the_transaction(self):
  result,row,calls,installed=self.run_loaded_base(manager_stack=True,blocked_package=True,touch_hold=True)
  self.assertEqual(result,2);self.assertIn('permission-held',' '.join(row['issues']))
  self.assertFalse(any('install' in c and '--dry-run' not in c for c,e in calls))
 def test_ignored_base_channel_pin_does_not_reject_approved_channel_plan(self):
  result,row,calls,installed=self.run_loaded_base(configured_pins=['defaults::certifi==2024.12.14'])
  self.assertEqual(result,0,row['issues']);self.assertEqual(row['ignored_pins'],['defaults::certifi==2024.12.14'])
  self.assertTrue(all('--no-pin' in c for c,e in calls if 'install' in c))
 def test_xkb_payload_is_staged_without_transaction_then_migrated(self):
  result,row,calls,installed=self.run_loaded_base(xkb_layout=True,xkb_uncached=True)
  self.assertEqual(result,0,row['issues']);self.assertEqual(row['xkb_migration']['status'],'installed-original-preserved')
  self.assertEqual(len([c for c,e in calls if '--download-only' in c]),1)
 def test_xkb_original_is_restored_when_install_fails(self):
  result,row,calls,installed=self.run_loaded_base(xkb_layout=True,fail_install=True)
  self.assertEqual(result,2);self.assertEqual(row['xkb_migration']['status'],'restored-after-failure')
  self.assertIn('Package installation failed',' '.join(row['issues']))
 def test_custom_xkb_data_stops_before_install(self):
  result,row,calls,installed=self.run_loaded_base(xkb_layout='custom')
  self.assertEqual(result,2);self.assertIn('untracked',' '.join(row['issues']));self.assertFalse(row['changes_started'])
  self.assertFalse(any('--yes' in c for c,e in calls))
 def test_full_base_update_prunes_unused_dependencies_and_verifies_actual_removal(self):
  result,row,calls,installed=self.run_loaded_base(prune_dependency=True)
  self.assertEqual(result,0,row['issues']);self.assertNotIn('legacy-runtime',installed)
  self.assertEqual([r['name'] for r in row['package_removals']],['legacy-runtime'])
  installs=[c for c,e in calls if 'install' in c]
  self.assertTrue(all('--prune' in c for c in installs))
  self.assertFalse(any(any('legacy-runtime' in arg for arg in c) for c in installs))
  result,row,calls,installed=self.run_loaded_base(prune_dependency=True,stale_removal=True)
  self.assertEqual(result,2);self.assertIn('Installed packages differ',' '.join(row['issues']))
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
