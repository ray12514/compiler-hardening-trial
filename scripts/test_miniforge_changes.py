import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('maintenance_changes',Path(__file__).with_name('patch_miniforge_trust.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class ChangeListTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.root=Path(self.temp.name).resolve();self.run=self.root/'run';self.run.mkdir()
  self.before={n:{'version':v,'build':b} for n,v,b in [('python','3.12.8','0'),('pip','26.2.2','0'),('same','1','0'),('old','1','0')]}
  self.after={n:{'version':v,'build':b} for n,v,b in [('python','3.12.9','0'),('pip','26.2.2','1'),('same','1','0'),('new','1','0')]}
 def save_summary(self,row):
  (self.run/'summary.json').write_text(json.dumps([row]));(self.run/'run.log').write_text('Mode: APPLY\n')
 def test_actual_snapshots_include_added_removed_version_build_and_unchanged(self):
  row={'prefix':'/shared/base','status':'updated','package_inventory_verified':True}
  self.save_summary(row)
  (self.run/'000-before-packages.json').write_text(json.dumps(self.before));(self.run/'000-after-packages.json').write_text(json.dumps(self.after))
  with contextlib.redirect_stdout(io.StringIO()):self.assertEqual(m.export_package_changes(self.run,self.root/'public'),0)
  report=json.loads((self.root/'public/manifest.json').read_text());rows=json.loads((self.root/'public/packages.json').read_text())
  self.assertEqual(report['evidence'],'verified-installed')
  self.assertEqual({r['status'] for r in rows},{'added','removed','changed-version','changed-build','unchanged'})
  self.assertNotIn(str(self.run),(self.root/'public/README.md').read_text())
  self.assertNotIn('upgraded',(self.root/'public/README.md').read_text())
 def test_older_promotion_can_be_reconstructed_without_original_stage_directory(self):
  identity={n:dict(r,subdir='linux-64',sha256='abc') for n,r in self.after.items()}
  digest=m.hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
  self.save_summary({'prefix':'/shared/base','status':'updated','changes_started':True,'promotion':{'status':'completed','manifest_sha256':digest,'stage':'/gone/private/stage'}})
  (self.run/'approved-promotion-plan.json').write_text(json.dumps({'prefix':'/shared/base','before':{n:[r['version'],r['build']] for n,r in self.before.items()},'packages':identity}))
  with contextlib.redirect_stdout(io.StringIO()):m.export_package_changes(self.run,self.root/'public')
  report=json.loads((self.root/'public/manifest.json').read_text())
  self.assertEqual(report['evidence'],'verified-installed');self.assertEqual(report['coverage'],'full inventory')
 def test_uncompleted_promotion_is_not_labeled_installed(self):
  self.save_summary({'prefix':'/shared/base','status':'previewed','changes_started':False,'promotion':{'status':'validated'}})
  with self.assertRaisesRegex(RuntimeError,'verified installed|insufficient'):m.export_package_changes(self.run,self.root/'public')
 def test_stage_export_is_visibly_candidate_only(self):
  (self.run/'stage-summary.json').write_text(json.dumps({'source_base':'/shared/base','status':'ready-for-review'}))
  (self.run/'source-packages.json').write_text(json.dumps(self.before));(self.run/'candidate-packages.json').write_text(json.dumps(self.after))
  with contextlib.redirect_stdout(io.StringIO()):m.export_package_changes(self.run,self.root/'public')
  self.assertIn('NOT INSTALLED',(self.root/'public/README.md').read_text())
  self.assertEqual(json.loads((self.root/'public/manifest.json').read_text())['evidence'],'candidate-only')
 def test_legacy_update_summary_is_explicitly_partial(self):
  self.save_summary({'prefix':'/base','status':'updated','package_changes':[{'name':'python','before':'3.12.8','after':'3.12.9'}],'package_removals':[{'name':'old','before':'1','status':'verified'}]})
  with contextlib.redirect_stdout(io.StringIO()):m.export_package_changes(self.run,self.root/'public')
  report=json.loads((self.root/'public/manifest.json').read_text())
  self.assertEqual(report['coverage'],'partial recorded changes; unchanged inventory unavailable')
  self.assertEqual(report['evidence'],'limited-installed-summary')
 def test_existing_public_output_is_not_overwritten(self):
  output=self.root/'public';output.mkdir();(output/'keep').write_text('existing')
  with self.assertRaisesRegex(RuntimeError,'new.*directory'):m.write_package_changes(output,self.before,self.after,{'evidence':'verified-installed'})
  self.assertEqual((output/'keep').read_text(),'existing')
 def test_export_requires_no_loaded_module_maintenance_group_or_network(self):
  with patch.object(m.sys,'argv',['script','--export-changes','/logs','--changes-output','/public']),patch.object(m,'export_package_changes',return_value=0) as export,patch.object(m,'find_base') as find,patch.object(m,'maintenance_gid') as group,patch.object(m.subprocess,'run') as run:
   self.assertEqual(m.main(),0)
  export.assert_called_once();find.assert_not_called();group.assert_not_called();run.assert_not_called()
 def test_automatic_export_is_connected_to_verified_base_update(self):
  from test_channel_regressions import BaseTransactionTests
  result,row,calls,installed=BaseTransactionTests().run_loaded_base(manager_stack=True)
  self.assertEqual(result,0,row['issues']);self.assertTrue(row['package_inventory_verified'])
  self.assertEqual(row['package_change_list']['evidence'],'verified-installed')
  self.assertGreater(row['package_change_list']['counts'].get('changed-version',0),0)
 def test_corrupt_older_approval_manifest_is_rejected(self):
  self.save_summary({'prefix':'/shared/base','status':'updated','changes_started':True,'promotion':{'status':'completed','manifest_sha256':'incorrect'}})
  (self.run/'approved-promotion-plan.json').write_text(json.dumps({'prefix':'/shared/base','before':{},'packages':self.after}))
  with self.assertRaisesRegex(RuntimeError,'does not match'):m.export_package_changes(self.run,self.root/'public')
 def test_permission_only_run_cannot_be_published_as_installed_package_changes(self):
  self.save_summary({'prefix':'/shared/base','status':'updated','mode':'permissions-only','package_changes':[]})
  with self.assertRaisesRegex(RuntimeError,'permission/certificate-only'):m.export_package_changes(self.run,self.root/'public')


if __name__=='__main__':unittest.main()
