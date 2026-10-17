"""Exercise the thin adapter with a real, optionally supplied ReFrame executable.

TRIAL_REFRAME_QA=/path/to/reframe python3 -m unittest discover -s tests -p test_production_reframe.py
Fixtures validate orchestration/reporting only; they are not performance evidence.
"""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.environ.get('TRIAL_REFRAME_QA'),'Set TRIAL_REFRAME_QA to prepared ReFrame 4.10.4')
class ReFrameAdapterTests(unittest.TestCase):
    def test_complete_and_partial_campaigns_have_different_reframe_outcomes(self):
        for status,native in (('finished',False),('budget_exhausted_partial',False),('finished',True)):
            with self.subTest(status=status,native=native), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp); pointer=root/'pointer.json'; campaign=root/'campaign'; campaign.mkdir()
                row={'condition':'2nodes-16rpn-fft','pairs':4,'full_mean_seconds':1.01,
                     'reference_mean_seconds':1.,'delta_seconds':.01,'runtime_increase_percent':1.,
                     'interval_low_percent':-.2,'interval_high_percent':2.}
                if native:
                    row={'condition':'2nodes-1rpn-osu_bw-1024B','pairs':4,'unit':'MB/s','full_mean':900.,
                         'reference_mean':1000.,'deterioration_percent':10.,'interval_low_percent':8.,'interval_high_percent':12.}
                (campaign/'summary.json').write_text(json.dumps({'status':status,'scope':'deployment','summaries':[row]}))
                command=[sys.executable,'-c',
                    'from pathlib import Path; import sys; Path(sys.argv[1]).write_text(sys.argv[2])',
                    str(pointer),json.dumps({'campaign':str(campaign)})]
                env=os.environ|{'TRIAL_PRODUCTION_COMMAND':json.dumps(command),'TRIAL_PRODUCTION_POINTER':str(pointer)}
                result=subprocess.run([os.environ['TRIAL_REFRAME_QA'],'-C',str(REPO/'production/reframe_settings.py'),
                    '-c',str(REPO/'production/reframe_check.py'),'-r','--exec-policy=serial','--performance-report',
                    '--prefix='+str(root/'rfm'),'--report-file='+str(root/'report.json')],
                    env=env,cwd=root,capture_output=True,text=True,timeout=60)
                self.assertEqual(result.returncode==0,status=='finished',result.stdout+result.stderr)
                report=json.loads((root/'report.json').read_text())
                serialized=json.dumps(report)
                self.assertIn('LibraryWorkflow',serialized)
                if status=='finished':
                    if native:
                        self.assertIn('2nodes-1rpn-osu_bw-1024B/deterioration_percent',serialized)
                        self.assertIn('MB/s',serialized)
                    else:
                        self.assertIn('2nodes-16rpn-fft/runtime_increase_percent',serialized)
                        self.assertIn('2nodes-16rpn-fft/interval_high_percent',serialized)


if __name__=='__main__':
    unittest.main()
