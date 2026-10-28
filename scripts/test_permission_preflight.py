import contextlib,csv,importlib.util,io,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('maintenance_permissions',Path(__file__).with_name('patch_miniforge_trust.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


@unittest.skipIf(os.geteuid()==0,'Root bypasses the user permission denials under test')
class PermissionPreflightTests(unittest.TestCase):
 def fixture(self,root):
  base=root/'base';(base/'conda-meta').mkdir(parents=True);(base/'bin').mkdir()
  (base/'bin/python').touch();(base/'bin/python').chmod(0o755);(base/'bin/conda').touch()
  (base/'conda-meta/history').write_text('original history')
  meta={'python':{'name':'python','version':'3.12.8','build':'0','files':[]},
        'alpha':{'name':'alpha','version':'1','build':'0','files':['one/a.dat','two/b.dat']},
        'beta':{'name':'beta','version':'1','build':'0','files':['three/c.dat']}}
  for folder,file in (('one','a.dat'),('two','b.dat'),('three','c.dat')):
   (base/folder).mkdir();(base/folder/file).write_text('original '+file)
  for name,record in meta.items():(base/'conda-meta'/(name+'.json')).write_text(json.dumps(record))
  return base,meta

 def audit(self,base,root,stage=None):
  with contextlib.redirect_stdout(io.StringIO()):return m.permission_audit(base,root,stage)

 def test_scanner_keeps_multiple_blockers_within_one_package_and_later_packages(self):
  with tempfile.TemporaryDirectory() as directory:
   base,meta=self.fixture(Path(directory));folders=[base/n for n in ('one','two','three')]
   for p in folders:p.chmod(0o555)
   try:
    holds=m.permission_holds(base,meta)
    self.assertEqual(set(holds),{'alpha','beta'})
    self.assertEqual({Path(p['path']).relative_to(base).as_posix() for p in holds['alpha']['blocked_paths']},{'one/a.dat','two/b.dat'})
    self.assertEqual(len(holds['beta']['blocked_paths']),1)
    self.assertEqual(len(list(m.hold_paths(holds))),3)
   finally:
    for p in folders:p.chmod(0o755)

 def test_reports_all_paths_by_actual_repair_owner_and_preserves_source(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);base,meta=self.fixture(root)
   for p in (base/'one',base/'two',base/'three'):p.chmod(0o555)
   before={str(p.relative_to(base)):(p.read_bytes(),p.stat().st_mode,p.stat().st_ino) for p in base.rglob('*') if p.is_file()}
   original=Path.lstat;first=os.geteuid()+100000;second=first+1;leaf=first+2
   def owners(path):
    st=original(path);uid=first if path in (base/'one',base/'two') else second if path==base/'three' else leaf if path==base/'one/a.dat' else None
    if uid is not None:
     values=list(st);values[4]=uid;return os.stat_result(values)
    return st
   try:
    with patch.object(Path,'lstat',owners):result=self.audit(base,root/'report')
    report=root/'report/permission-preflight'
    with (report/'permissions.csv').open() as stream:rows=list(csv.DictReader(stream))
    affected={row['path']:row for row in rows}
    self.assertEqual(set(affected),{str(base/p) for p in ('one/a.dat','two/b.dat','three/c.dat')})
    self.assertEqual(affected[str(base/'one/a.dat')]['uid'],str(first));self.assertEqual(affected[str(base/'one/a.dat')]['file_uid'],str(leaf))
    self.assertEqual(affected[str(base/'one/a.dat')]['blocking_path'],str(base/'one'))
    self.assertTrue((report/('permissions-owner-%d.txt'%first)).is_file());self.assertTrue((report/('permissions-owner-%d.txt'%second)).is_file())
    self.assertIn(str(base/'two/b.dat'),(report/('permissions-owner-%d.txt'%first)).read_text())
    self.assertEqual(result['summary']['repair_target_count'],3)
    self.assertEqual(before,{str(p.relative_to(base)):(p.read_bytes(),p.stat().st_mode,p.stat().st_ino) for p in base.rglob('*') if p.is_file()})
    self.assertEqual((root/'report').stat().st_mode&0o777,0o700)
    self.assertTrue(all(p.stat().st_mode&0o077==0 for p in report.iterdir() if p.is_file()))
   finally:
    for p in (base/'one',base/'two',base/'three'):p.chmod(0o755)

 def test_unreadable_and_malformed_metadata_do_not_hide_later_valid_packages(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);base,meta=self.fixture(root)
   unreadable=base/'conda-meta/00-unreadable.json';unreadable.write_text('{}');unreadable.chmod(0)
   (base/'conda-meta/01-bad.json').write_text('bad JSON')
   (base/'three').chmod(0o555)
   try:
    result=self.audit(base,root/'report')
    self.assertGreaterEqual(result['summary']['inspection_gap_count'],2)
    self.assertIn(str(base/'three'),{t['path'] for t in result['summary']['targets']})
    self.assertEqual(result['summary']['installed_packages_inspected'],3)
   finally:unreadable.chmod(0o644);(base/'three').chmod(0o755)

 def test_untraversable_tree_is_reported_as_uninspected_and_siblings_continue(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);base,meta=self.fixture(root);(base/'one').chmod(0);(base/'three').chmod(0o555)
   try:
    result=self.audit(base,root/'report');targets={t['path']:t for t in result['summary']['targets']}
    self.assertTrue(targets[str(base/'one')]['uninspected_contents'])
    self.assertIn(str(base/'three'),targets);self.assertIn(str(base/'one'),result['summary']['uninspected_directories'])
    self.assertGreater(result['summary']['inspection_gap_count'],0)
   finally:(base/'one').chmod(0o755);(base/'three').chmod(0o755)

 def test_control_file_denial_and_package_denial_are_both_reported(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);base,meta=self.fixture(root);history=base/'conda-meta/history';history.chmod(0o444);(base/'two').chmod(0o555)
   try:
    result=self.audit(base,root/'report');paths={p for t in result['summary']['targets'] for p in t['affected_paths']}
    self.assertIn(str(history),paths);self.assertIn(str(base/'two/b.dat'),paths)
   finally:history.chmod(0o644);(base/'two').chmod(0o755)

 def test_cache_rename_is_only_a_review_option_and_nothing_is_moved(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);base,meta=self.fixture(root);folder=base/'bin/__pycache__';folder.mkdir()
   source=base/'bin/android_deploy.py';source.write_text('pass')
   cache=folder/'android_deploy.cpython-312.pyc';cache.write_bytes(b'original cache')
   meta['alpha']['files'].append('bin/android_deploy.py');(base/'conda-meta/alpha.json').write_text(json.dumps(meta['alpha']))
   folder.chmod(0o555)
   try:
    result=self.audit(base,root/'report');target=next(t for t in result['summary']['targets'] if t['path']==str(folder))
    self.assertIn('preserving the old cache directory by rename',target['advice'])
    self.assertEqual(cache.read_bytes(),b'original cache');self.assertEqual(folder.stat().st_mode&0o777,0o555)
    self.assertTrue(any(p['exists'] is False for p in json.loads((root/'report/permission-preflight/permissions.json').read_text())['paths']))
   finally:folder.chmod(0o755)

 def test_cli_audit_is_read_only_without_group_checks_or_conda_execution(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);base,meta=self.fixture(root)
   with patch.object(m.sys,'argv',['script',str(base),'--check-permissions','--log-dir',str(root/'report')]),patch.object(m,'maintenance_gid') as group,patch.object(m.subprocess,'run') as run,contextlib.redirect_stdout(io.StringIO()):
    self.assertEqual(m.main(),0)
   group.assert_not_called();run.assert_not_called()

 def test_promotion_collects_multiple_required_problems_before_any_source_changes(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);base,meta=self.fixture(root);stage=root/'stage';stage.mkdir()
   proposed={n:dict(r,version='2') for n,r in meta.items()}
   (stage/'stage-summary.json').write_text(json.dumps({'source_base':str(base)}));(stage/'candidate-packages.json').write_text(json.dumps(proposed))
   for p in (base/'one',base/'two',base/'three'):p.chmod(0o555)
   try:
    with patch.object(m.sys,'argv',['script',str(base),'--promote',str(stage),'--apply','--log-dir',str(root/'report')]),patch.object(m,'load_promotion') as load,patch.object(m,'maintenance_gid') as group,patch.object(m.subprocess,'run') as run,contextlib.redirect_stdout(io.StringIO()):
     self.assertEqual(m.main(),2)
    load.assert_not_called();group.assert_not_called();run.assert_not_called()
    result=json.loads((root/'report/permission-summary.json').read_text())
    self.assertEqual(result['repair_target_count'],3);self.assertGreaterEqual(result['promotion_blocking_path_count'],3)
    self.assertEqual((base/'conda-meta/history').read_text(),'original history')
   finally:
    for p in (base/'one',base/'two',base/'three'):p.chmod(0o755)

 def test_readonly_file_in_writable_parent_is_not_a_package_replacement_blocker(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);base,meta=self.fixture(root);(base/'one/a.dat').chmod(0o444)
   self.assertEqual(self.audit(base,root/'report')['summary']['affected_path_count'],0)

 def test_candidate_new_path_under_blocked_directory_is_checked_too(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);base,meta=self.fixture(root);stage=root/'stage';stage.mkdir()
   proposed={'new-app':{'name':'new-app','version':'1','build':'0','files':['one/new-file.dat']}}
   (stage/'stage-summary.json').write_text(json.dumps({'source_base':str(base)}));(stage/'candidate-packages.json').write_text(json.dumps(proposed))
   (base/'one').chmod(0o555)
   try:
    result=self.audit(base,root/'report',stage)
    paths=json.loads((root/'report/permission-preflight/permissions.json').read_text())['paths']
    row=next(p for p in paths if p['package']=='new-app')
    self.assertEqual(row['path'],str(base/'one/new-file.dat'));self.assertIs(row['exists'],False)
    self.assertIn('candidate package',row['phases']);self.assertTrue(row['required_for_promotion'])
   finally:(base/'one').chmod(0o755)

 def test_unchanged_package_blockers_are_reported_without_claiming_they_must_be_replaced(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);base,meta=self.fixture(root);stage=root/'stage';stage.mkdir()
   (stage/'stage-summary.json').write_text(json.dumps({'source_base':str(base)}));(stage/'candidate-packages.json').write_text(json.dumps(meta))
   (base/'one').chmod(0o555)
   try:
    result=self.audit(base,root/'report',stage)
    self.assertGreater(result['summary']['affected_path_count'],0)
    self.assertEqual(result['summary']['promotion_blocking_path_count'],0)
   finally:(base/'one').chmod(0o755)

 def test_malformed_candidate_inventory_does_not_hide_installed_blockers(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);base,meta=self.fixture(root);stage=root/'stage';stage.mkdir()
   (stage/'stage-summary.json').write_text(json.dumps({'source_base':str(base)}))
   (stage/'candidate-packages.json').write_text(json.dumps(['alpha']))
   (base/'one').chmod(0o555)
   try:
    result=self.audit(base,root/'report',stage)
    self.assertIn(str(base/'one'),{t['path'] for t in result['summary']['targets']})
    self.assertGreaterEqual(result['summary']['inspection_gap_count'],1)
    self.assertGreaterEqual(result['summary']['promotion_blocking_path_count'],2)
    self.assertEqual(result['summary']['candidate_packages_inspected'],0)
   finally:(base/'one').chmod(0o755)

 def test_sticky_parent_does_not_get_a_cache_rename_suggestion_for_foreign_owners(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);base,meta=self.fixture(root);folder=base/'bin/__pycache__';folder.mkdir();folder.chmod(0o555)
   (base/'bin').chmod(0o1777);(base/'bin/android_deploy.py').write_text('pass')
   meta['alpha']['files'].append('bin/android_deploy.py');(base/'conda-meta/alpha.json').write_text(json.dumps(meta['alpha']))
   original=Path.lstat
   def foreign(path):
    st=original(path)
    if path in (folder,base/'bin'):
     values=list(st);values[4]=os.geteuid()+100000;return os.stat_result(values)
    return st
   try:
    with patch.object(Path,'lstat',foreign):result=self.audit(base,root/'report')
    target=next(t for t in result['summary']['targets'] if t['path']==str(folder))
    self.assertNotIn('by rename',target['advice'])
   finally:folder.chmod(0o755);(base/'bin').chmod(0o755)

 def test_report_latest_uses_summary_time_and_does_not_rescan(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);base,meta=self.fixture(root);logs=root/'.cse-trust-logs';logs.mkdir()
   audit=self.audit(base,logs/'permissions-old');new=logs/'new-normal';new.mkdir()
   (new/'summary.json').write_text('[]')
   os.utime(logs/'permissions-old/permission-summary.json',ns=(1,1));os.utime(new/'summary.json',ns=(2,2))
   with patch.object(Path,'home',return_value=root):self.assertEqual(m.report_directory('latest'),new)
   with patch.object(m,'permission_audit') as scan,patch.object(m.subprocess,'run') as run,contextlib.redirect_stdout(io.StringIO()):
    self.assertEqual(m.report_existing(audit['root']),0)
   scan.assert_not_called();run.assert_not_called()


if __name__=='__main__':unittest.main()
