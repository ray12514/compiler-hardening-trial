"""The shareable page must preserve partial coverage, scope, pairing and privacy."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

REPO=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(REPO/'production'),str(REPO/'scripts')]
import team_summary


class TeamSummaryTests(unittest.TestCase):
    def generate(self, argv):
        with contextlib.redirect_stdout(io.StringIO()): return team_summary.main(argv)

    def test_screenshot_counts_preserve_missing_cases_and_do_not_invent_intervals(self):
        with tempfile.TemporaryDirectory() as tmp:
            value=self.generate(['--evidence',str(REPO/'reports/2026-10-16/evidence.json'),'--output-dir',tmp])
            self.assertEqual((value['complete'],value['partial'],value['not_measured']),(12,1,3))
            self.assertEqual(value['paired_comparisons'],124)
            self.assertIsNone(value['loop_seconds_range'])
            self.assertEqual(value['range'],[-2.597,1.323])
            self.assertTrue(all(row['low'] is None for row in value['conditions']))
            self.assertTrue(all(row['change'] is None for row in value['conditions'] if row['status']=='not measured'))
            self.assertIn('4/10 pairs',(Path(tmp)/'team-summary.svg').read_text())

    def fixture(self, root, scope='deployment'):
        directory=root/'20261021-private-host-job999'; directory.mkdir()
        case={'mode':'fft','nodes':20,'ranks_per_node':88,'status':'passed','pairs':[
            {'status':'passed','results':{'full':{'loop_seconds':1.02},'reference':{'loop_seconds':1}}} for _ in range(4)]}
        value={'scope':scope,'conditions':[case],'requested_pairs':4,'seed':21,'hosts':['SECRET-HOST'],'job_id':'SECRET-JOB'}
        (directory/'manifest.json').write_text(json.dumps(value)); return directory,value

    def test_original_pairs_get_intervals_and_export_no_private_identifiers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); directory,value=self.fixture(root)
            value['conditions'][0]['pairs'].append({'status':'running','results':{'full':{'loop_seconds':99}}})
            (directory/'manifest.json').write_text(json.dumps(value))
            result=self.generate(['--campaign',str(directory),'--output-dir',str(root/'out')])
            self.assertAlmostEqual(result['conditions'][0]['change'],2)
            self.assertAlmostEqual(result['conditions'][0]['low'],2)
            self.assertEqual(result['conditions'][0]['pairs'],4)
            self.assertEqual(result['loop_seconds_range'],[1,1.02])
            exported=''.join(p.read_text() for p in (root/'out').iterdir())
            for private in ('SECRET-HOST','SECRET-JOB','private-host-job999',str(root)):
                self.assertNotIn(private,exported)

    def test_audit_claim_requires_a_passed_historical_match_and_scopes_cannot_mix(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); directory,value=self.fixture(root)
            audit=root/'audit.json'; audit.write_text(json.dumps({'status':'passed','historical_results':[{'directory':str(directory),'status':'matched'}]}))
            result=self.generate(['--campaign',str(directory),'--audit',str(audit),'--output-dir',str(root/'out')])
            self.assertIn('passed',result['build_verification'])
            other=root/'other'; other.mkdir(); (other/'manifest.json').write_text(json.dumps(value|{'scope':'stack'}))
            with self.assertRaisesRegex(ValueError,'separate pages'):
                self.generate(['--campaign',str(directory),'--campaign',str(other),'--output-dir',str(root/'out')])
            with self.assertRaisesRegex(ValueError,'Duplicate'):
                self.generate(['--campaign',str(directory),'--campaign',str(directory),'--output-dir',str(root/'out')])


if __name__=='__main__': unittest.main()
