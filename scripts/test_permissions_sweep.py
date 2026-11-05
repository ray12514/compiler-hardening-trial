"""The standalone permission repair must include legacy envs and package caches."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import tarfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('maintenance_sweep',Path(__file__).with_name('patch_miniforge_trust.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class FullPermissionSweepTests(unittest.TestCase):
 def fixture(self,root):
  base=root/'miniforge';paths=[]
  for relative in ('lib/python3.14/site-packages/jedi/constants.pyi',
                   'envs/old-python/conda-meta/history','envs/old-python/lib/python3.10/site-packages/jedi/constants.pyi',
                   'legacy-prefix/conda-meta/history','legacy-prefix/lib/older.pyi',
                   'pkgs/old-package-1-0/lib/older.pyi'):
   path=base/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('preserve '+relative);path.chmod(0o600);paths.append(path)
  return base,paths

 def run_repair(self,root,base,apply):
  args=SimpleNamespace(log_dir=root/('apply' if apply else 'preview'),apply=apply,verbose=False)
  with patch.object(m,'maintenance_gid',return_value=os.getegid()),patch.object(m.subprocess,'run',side_effect=AssertionError('No package commands allowed')),contextlib.redirect_stdout(io.StringIO()) as output:
   result=m.permissions_only(args,base)
  return result,json.loads((args.log_dir/'summary.json').read_text())[0],output.getvalue()

 def test_existing_command_repairs_base_legacy_envs_nested_prefixes_and_cache(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);base,paths=self.fixture(root);before={p:p.read_bytes() for p in paths}
   result,row,output=self.run_repair(root,base,True);self.assertEqual(result,0)
   for path in paths:
    with self.subTest(path=path.relative_to(base)):
     self.assertEqual(path.stat().st_mode&0o777,0o664,'Permission sweep skipped '+str(path.relative_to(base)))
     self.assertEqual(path.stat().st_gid,os.getegid());self.assertEqual(path.read_bytes(),before[path])

 def test_exact_docker_credentials_stub_and_group_only_sibling_are_repaired(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);base=root/'miniforge'
   docker=base/'lib/python3.14/site-packages/jedi/third_party/typeshed/stubs/docker/docker'
   stub=docker/'credentials/constants.pyi';stub.parent.mkdir(parents=True);stub.write_text('DEFAULT: str\n');stub.chmod(0o600)
   sibling=docker/'constants.pyi';sibling.write_text('VALUE: int\n');sibling.chmod(0o664)
   alternate=next((group for group in os.getgroups() if group!=os.getegid()),None)
   if alternate is None:self.skipTest('A second account group is needed for a real chgrp regression')
   for path in (stub.parent,stub,sibling):os.chown(path,-1,alternate)
   before={p:(p.read_bytes(),p.stat().st_uid) for p in (stub,sibling)}
   result,row,output=self.run_repair(root,base,True);self.assertEqual(result,0)
   for path in (stub,sibling):
    with self.subTest(path=path.relative_to(base)):
     self.assertEqual(path.stat().st_gid,os.getegid(),'Wrong group on '+str(path.relative_to(base)))
     self.assertEqual(path.stat().st_mode&0o777,0o664)
     self.assertEqual((path.read_bytes(),path.stat().st_uid),before[path])
   self.assertEqual(stub.parent.stat().st_gid,os.getegid())
   self.assertFalse(any(entry['path']==str(stub.parent) and entry['stage']=='protected' for entry in row['skipped_paths']))

 def test_preview_preserves_all_file_bytes_and_metadata(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);base,paths=self.fixture(root)
   before={p:(p.read_bytes(),p.stat().st_mode,p.stat().st_uid,p.stat().st_gid,p.stat().st_ino) for p in paths}
   result,row,output=self.run_repair(root,base,False);self.assertEqual(result,0)
   self.assertEqual(before,{p:(p.read_bytes(),p.stat().st_mode,p.stat().st_uid,p.stat().st_gid,p.stat().st_ino) for p in paths})

 def test_internal_cache_env_hardlinks_are_updated_in_place_without_payload_copies(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);base,paths=self.fixture(root);source=base/'pkgs/shared/lib/common.pyi';source.parent.mkdir(parents=True)
   source.write_text('common stub');source.chmod(0o600);alias=base/'envs/old-python/lib/common.pyi';alias.parent.mkdir(parents=True,exist_ok=True);os.link(source,alias)
   inode=source.stat().st_ino
   with patch.object(m.shutil,'copy2',side_effect=AssertionError('Internal links should not copy payloads')):
    result,row,output=self.run_repair(root,base,True)
   self.assertEqual(result,0);self.assertEqual(source.stat().st_ino,inode);self.assertEqual(alias.stat().st_ino,inode)
   self.assertEqual(source.stat().st_mode&0o777,0o664);self.assertEqual(alias.read_text(),'common stub')
   self.assertEqual(row['permissions']['internal_hardlink_groups'],1)

 def test_outside_hardlinks_keep_their_original_permissions(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);base,paths=self.fixture(root);outside=root/'private-user-file';outside.write_text('external original');outside.chmod(0o600)
   cache=base/'pkgs/linked/file';cache.parent.mkdir(parents=True);os.link(outside,cache)
   alias=base/'envs/old-python/linked-file';os.link(outside,alias);original=outside.stat()
   with patch.object(m.shutil,'copy2',wraps=m.shutil.copy2) as copy:
    result,row,output=self.run_repair(root,base,True)
   self.assertEqual(result,0);self.assertEqual(copy.call_count,1)
   self.assertEqual(cache.stat().st_ino,alias.stat().st_ino)
   self.assertEqual((outside.stat().st_ino,outside.stat().st_mode,outside.stat().st_gid),(original.st_ino,original.st_mode,original.st_gid))
   self.assertEqual(cache.stat().st_mode&0o777,0o664);self.assertEqual(alias.stat().st_mode&0o777,0o664)
   self.assertNotEqual(cache.stat().st_ino,outside.stat().st_ino);self.assertEqual(outside.read_text(),'external original')
   self.assertEqual(row['permissions']['detached_paths'],2)

 def test_credentials_and_backups_get_group_access_while_external_targets_are_preserved(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);base,paths=self.fixture(root)
   secret=base/'.condarc';secret.write_text('private config');secret.chmod(0o600)
   backup=base/m.PATH_BACKUPS/'old';backup.parent.mkdir(parents=True);backup.write_text('recovery');backup.chmod(0o600)
   outside=root/'outside-env';outside.mkdir();external=outside/'keep';external.write_text('outside');external.chmod(0o600)
   (base/'envs/external-env').symlink_to(outside,target_is_directory=True)
   original={p:(p.read_bytes(),p.stat().st_mode,p.stat().st_uid) for p in (external,)}
   result,row,output=self.run_repair(root,base,True);self.assertEqual(result,0)
   self.assertEqual(original,{p:(p.read_bytes(),p.stat().st_mode,p.stat().st_uid) for p in (external,)})
   self.assertEqual(secret.stat().st_mode&0o777,0o660);self.assertEqual(secret.stat().st_gid,os.getegid())
   self.assertEqual(backup.stat().st_mode&0o777,0o660)
   self.assertGreaterEqual(row['permissions']['protected'],1)
   protected={r['path'] for r in row['skipped_paths'] if r['stage']=='protected'}
   self.assertNotIn(str(secret),protected);self.assertNotIn(str(base/m.PATH_BACKUPS),protected);self.assertIn(str(base/'envs/external-env'),protected)

 def test_whole_tree_repairs_x11_hidden_backup_and_all_owned_owner_group_bits(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);base,paths=self.fixture(root)
   backup=base/m.PATH_BACKUPS/'20261105/xkb/geometry/.file'
   backup.parent.mkdir(parents=True);backup.write_text('old X11 data');backup.chmod(0o400)
   dot=base/'.hidden/nested/.another';dot.parent.mkdir(parents=True);dot.write_text('hidden');dot.chmod(0o600)
   git=base/'.git/objects/ab/.object';git.parent.mkdir(parents=True);git.write_text('object');git.chmod(0o400)
   alternate=next((group for group in os.getgroups() if group!=os.getegid()),None)
   if alternate is None:self.skipTest('A second account group is needed for a real chgrp regression')
   for path in (backup,backup.parent,base/m.PATH_BACKUPS,dot,git):os.chown(path,-1,alternate)
   before={p:p.read_bytes() for p in (backup,dot,git)}
   self.run_repair(root,base,False)
   self.assertEqual(backup.stat().st_mode&0o777,0o400)
   self.assertEqual(backup.stat().st_gid,alternate)
   result,row,output=self.run_repair(root,base,True);self.assertEqual(result,0)
   for path in (base,*base.rglob('*')):
    st=path.lstat()
    self.assertEqual(st.st_gid,os.getegid(),str(path))
    self.assertEqual((st.st_mode>>6)&7,(st.st_mode>>3)&7,str(path))
    self.assertEqual(st.st_uid,os.geteuid())
   self.assertEqual(before,{p:p.read_bytes() for p in before})
   self.assertFalse(any(item['stage']=='protected' for item in row['skipped_paths']))
   archive=root/'miniforge.tar'
   with tarfile.open(archive,'w') as stream:stream.add(base,arcname='.')
   with tarfile.open(archive) as stream:
    for path in before:self.assertIn('./'+str(path.relative_to(base)),stream.getnames())

 def test_owned_special_mode_file_and_fifo_are_included_in_full_repair(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);base,paths=self.fixture(root)
   executable=base/'bin/legacy';executable.parent.mkdir();executable.write_text('legacy');executable.chmod(0o4755)
   fifo=base/'.fifo';os.mkfifo(fifo,0o600)
   result,row,output=self.run_repair(root,base,True);self.assertEqual(result,0)
   for path in (executable,fifo):
    self.assertEqual(path.stat().st_gid,os.getegid())
    self.assertEqual((path.stat().st_mode>>6)&7,(path.stat().st_mode>>3)&7)
    self.assertFalse(any(item['path']==str(path) for item in row['skipped_paths']))

 def test_owned_acl_file_gets_group_acl_repaired_instead_of_being_skipped(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);base,paths=self.fixture(root);target=paths[0];skipped=[]
   target.chmod(0o664);os.chown(target,-1,os.getegid())
   def attributes(path):return ['system.posix_acl_access'] if Path(path)==target else []
   with patch.object(m,'maintenance_gid',return_value=os.getegid()),patch.object(m.os,'listxattr',side_effect=attributes,create=True),patch.object(m.shutil,'which',return_value='/usr/bin/setfacl'),patch.object(m.subprocess,'run',return_value=SimpleNamespace(returncode=0,stderr='')) as run:
    m.public_permissions(base,base,False,lambda message:None,skipped,whole_tree=True)
    run.assert_not_called()
    m.public_permissions(base,base,True,lambda message:None,skipped,whole_tree=True)
   run.assert_called_once()
   self.assertEqual(run.call_args.args[0],['/usr/bin/setfacl','-m','g::rw-,m::rw-','--',str(target)])
   self.assertEqual(target.stat().st_mode&0o777,0o664)
   self.assertFalse(any(item['path']==str(target) for item in skipped))

 def test_missing_acl_tool_is_reported_for_the_actual_path(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);base,paths=self.fixture(root);target=paths[0];skipped=[]
   def attributes(path):return ['system.posix_acl_access'] if Path(path)==target else []
   with patch.object(m,'maintenance_gid',return_value=os.getegid()),patch.object(m.os,'listxattr',side_effect=attributes,create=True),patch.object(m.shutil,'which',return_value=None),patch.object(m.subprocess,'run',side_effect=AssertionError('No command without ACL tool')):
    m.public_permissions(base,base,True,lambda message:None,skipped,whole_tree=True)
   self.assertTrue(any(item['path']==str(target) and 'requires setfacl' in item['reason'] for item in skipped))

 def test_python_namespaces_are_public_and_actual_credentials_have_group_only_access(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);base,paths=self.fixture(root);modules=[]
   for relative in ('lib/python3.14/site-packages/sample/credentials/constants.pyi',
                    'envs/old/lib/python3.10/site-packages/sample/tokens/__init__.py',
                    'pkgs/old-package/site-packages/sample/secrets/constants.pyi',
                    'legacy/lib/python3.11/dist-packages/sample/credentials/constants.pyi'):
    path=base/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('public package code');path.chmod(0o600);modules.append(path)
   private=[]
   for relative in ('credentials/account.json', '.aws/credentials',
                    'lib/python3.14/site-packages/sample/credentials/client.key',
                    'lib/python3.14/site-packages/sample/credentials/.env',
                    'lib/python3.14/site-packages/sample/credentials/credentials'):
    path=base/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('private data');path.chmod(0o600);private.append(path)
   result,row,output=self.run_repair(root,base,True);self.assertEqual(result,0)
   for path in modules:self.assertEqual(path.stat().st_mode&0o777,0o664,str(path))
   for path in private:self.assertEqual(path.stat().st_mode&0o777,0o660,str(path))

 def test_nested_credential_files_and_directories_get_cse_group_access(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);base,paths=self.fixture(root)
   folder=base/'envs/old-python/.aws/nested';folder.mkdir(parents=True)
   credential=folder/'account.json';credential.write_text('credential data');credential.chmod(0o600)
   executable=folder/'helper';executable.write_text('helper');executable.chmod(0o700)
   alternate=next((group for group in os.getgroups() if group!=os.getegid()),None)
   if alternate is None:self.skipTest('A second account group is needed for a real chgrp regression')
   for path in (folder.parent,folder,credential,executable):os.chown(path,-1,alternate)
   result,row,output=self.run_repair(root,base,True);self.assertEqual(result,0)
   for path in (folder.parent,folder,credential,executable):
    self.assertEqual(path.stat().st_gid,os.getegid(),str(path))
    self.assertEqual(path.stat().st_uid,os.geteuid())
   self.assertEqual(folder.stat().st_mode&0o777,0o770)
   self.assertEqual(credential.stat().st_mode&0o777,0o660)
   self.assertEqual(executable.stat().st_mode&0o777,0o770)
   self.assertEqual(credential.read_text(),'credential data')

 def test_shared_inode_with_public_and_private_names_gets_each_required_mode(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);base,paths=self.fixture(root)
   public=base/'lib/public.py';public.write_text('same bytes');public.chmod(0o600)
   private=base/'.aws/credentials';private.parent.mkdir();os.link(public,private)
   result,row,output=self.run_repair(root,base,True);self.assertEqual(result,0)
   self.assertEqual(public.stat().st_mode&0o777,0o664)
   self.assertEqual(private.stat().st_mode&0o777,0o660)
   self.assertNotEqual(public.stat().st_ino,private.stat().st_ino)
   self.assertEqual(public.read_bytes(),private.read_bytes())

 def test_foreign_owned_legacy_file_is_reported_for_owner_review(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);base,paths=self.fixture(root);target=paths[1];original=Path.lstat
   def foreign(path):
    value=original(path)
    if path==target:
     fields=list(value);fields[4]=os.geteuid()+1000;return os.stat_result(fields)
    return value
   with patch.object(Path,'lstat',foreign):result,row,output=self.run_repair(root,base,True)
   self.assertEqual(result,0);self.assertEqual(target.stat().st_mode&0o777,0o600)
   self.assertTrue(any(item['path']==str(target) and 'owner UID' in item['reason'] for item in row['skipped_paths']))
   self.assertEqual(row['status'],'updated-with-skips')

 def test_owned_locked_legacy_directory_is_repaired_then_its_contents_are_walked(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);base,paths=self.fixture(root);folder=base/'envs/locked';folder.mkdir();file=folder/'old.pyi';file.write_text('locked');file.chmod(0o600);folder.chmod(0)
   try:
    result,row,output=self.run_repair(root,base,True)
    self.assertEqual(result,0);self.assertEqual(folder.stat().st_mode&0o777,0o775);self.assertEqual(file.stat().st_mode&0o777,0o664)
    if not folder.stat().st_mode&0o2000:self.assertTrue(any('did not persist' in item['reason'] for item in row['skipped_paths']))
   finally:folder.chmod(0o700)

 def test_second_sweep_makes_no_changes_when_already_compliant(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);base,paths=self.fixture(root)
   # Model Linux's directory setgid metadata when the local test filesystem
   # strips that bit; files and all recursive traversal remain real.
   original=Path.lstat
   def directory_setgid(path):
    value=original(path)
    if m.stat.S_ISDIR(value.st_mode):
     fields=list(value);fields[0]|=m.stat.S_ISGID;return os.stat_result(fields)
    return value
   with patch.object(Path,'lstat',directory_setgid):self.run_repair(root,base,True)
   next_root=root/'second';next_root.mkdir()
   with patch.object(Path,'lstat',directory_setgid),patch.object(m.os,'chmod',wraps=m.os.chmod) as chmod:
    result,row,output=self.run_repair(next_root,base,True)
   self.assertEqual(result,0);self.assertEqual(row['permissions']['changed'],0)
   self.assertFalse(any(str(call.args[0]).startswith(str(base)) for call in chmod.call_args_list))

 def test_filesystem_ignoring_a_requested_mode_is_reported_instead_of_claiming_success(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);base,paths=self.fixture(root);target=paths[0];original=m.os.chmod
   def ignore_target(path,mode,*args,**kwargs):
    if Path(path)!=target:return original(path,mode,*args,**kwargs)
   with patch.object(m.os,'chmod',side_effect=ignore_target):result,row,output=self.run_repair(root,base,True)
   self.assertEqual(target.stat().st_mode&0o777,0o600)
   self.assertTrue(any(item['path']==str(target) and 'did not persist' in item['reason'] for item in row['skipped_paths']))
   self.assertEqual(row['status'],'updated-with-skips')

 def test_saved_report_names_the_whole_tree_scope_without_commands_or_new_changes(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);base,paths=self.fixture(root);self.run_repair(root,base,True)
   before={p:(p.stat().st_mode,p.stat().st_uid,p.stat().st_gid) for p in paths}
   with patch.object(m.subprocess,'run',side_effect=AssertionError('Read-only report')),contextlib.redirect_stdout(io.StringIO()) as output:
    self.assertEqual(m.main(['--report',str(root/'apply')]),0)
   self.assertIn('entire-miniforge-tree',output.getvalue())
   self.assertEqual(before,{p:(p.stat().st_mode,p.stat().st_uid,p.stat().st_gid) for p in paths})

 def test_regular_base_update_still_leaves_other_environments_and_cache_metadata_alone(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);base,paths=self.fixture(root)
   with patch.object(m,'maintenance_gid',return_value=os.getegid()):m.public_permissions(base,base,True,lambda value:None)
   self.assertEqual(paths[0].stat().st_mode&0o777,0o664)
   for path in paths[1:]:self.assertEqual(path.stat().st_mode&0o777,0o600)


if __name__=='__main__':unittest.main()
