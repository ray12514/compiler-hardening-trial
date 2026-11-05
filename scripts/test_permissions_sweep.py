"""The standalone permission repair must include legacy envs and package caches."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
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

 def test_credentials_backups_and_external_directory_targets_are_reported_and_preserved(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);base,paths=self.fixture(root)
   secret=base/'.condarc';secret.write_text('private config');secret.chmod(0o600)
   backup=base/m.PATH_BACKUPS/'old';backup.parent.mkdir(parents=True);backup.write_text('recovery');backup.chmod(0o600)
   outside=root/'outside-env';outside.mkdir();external=outside/'keep';external.write_text('outside');external.chmod(0o600)
   (base/'envs/external-env').symlink_to(outside,target_is_directory=True)
   original={p:(p.read_bytes(),p.stat().st_mode,p.stat().st_uid) for p in (secret,backup,external)}
   result,row,output=self.run_repair(root,base,True);self.assertEqual(result,0)
   self.assertEqual(original,{p:(p.read_bytes(),p.stat().st_mode,p.stat().st_uid) for p in (secret,backup,external)})
   self.assertGreaterEqual(row['permissions']['protected'],3)
   protected={r['path'] for r in row['skipped_paths'] if r['stage']=='protected'}
   self.assertIn(str(secret),protected);self.assertIn(str(base/m.PATH_BACKUPS),protected);self.assertIn(str(base/'envs/external-env'),protected)

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
