"""Execute the real Bash batch flow with a recording driver, without allocating nodes."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

REPO=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(REPO/'production'),str(REPO/'scripts')]
import campaign

STUB=r'''
import json, os, socket, sys
from pathlib import Path
root=Path(os.environ['TRIAL_ROOT']); args=sys.argv[1:]
with (root/'calls.jsonl').open('a') as stream: stream.write(json.dumps({'args':args,'cpu':os.environ.get('CPUSET')})+'\n')
if '--result-pointer' in args:
    pointer=Path(args[args.index('--result-pointer')+1])
    if args[0]=='audit':
        out=root/'audit'; out.mkdir(exist_ok=True)
        (out/'audit.json').write_text('{}'); pointer.write_text(json.dumps({'audit':str(out)}))
    else:
        out=root/('placement' if '--audit-only' in args else 'production'); out.mkdir(exist_ok=True)
        (out/'manifest.json').write_text(json.dumps({'conditions':[{'layout':'layout.json'}]}))
        (out/'layout.json').write_text(json.dumps({'hosts':{socket.gethostname().split('.')[0]:{'cpus':[7]}}}))
        pointer.write_text(json.dumps({'campaign':str(out)}))
if args[0]=='production' and '--reframe' in args and os.environ.get('TEST_PARTIAL')=='1': sys.exit(1)
'''


class BatchTests(unittest.TestCase):
    def execute(self, partial):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'runner').mkdir()
            trial=root/'runner/trial'; trial.write_text('#!'+sys.executable+'\n'+STUB); trial.chmod(0o755)
            result=subprocess.run(['bash',str(REPO/'scripts/run_20_node_campaign.sh')],env=os.environ|{
                'TRIAL_ROOT':str(root),'IO_DIR':str(root/'io'),'SLURM_JOB_ID':'123','SLURM_JOB_NUM_NODES':'20',
                'CAMPAIGN_NODES':'20','FFT_MIB_PER_RANK':'1','IO_MIB_PER_RANK':'1','MAX_CHECKPOINT_GIB':'16',
                'RUN_SERIAL':'1','RUN_OSU':'1','TEST_PARTIAL':str(int(partial))},capture_output=True,text=True,timeout=30)
            calls=[json.loads(line) for line in (root/'calls.jsonl').read_text().splitlines()]
            return result,calls

    def test_twenty_node_flow_audits_and_runs_packages_before_osu_without_downloads(self):
        result,calls=self.execute(False)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        commands=[v['args'] for v in calls]
        production=next(c for c in commands if c[0]=='production' and '--reframe' in c)
        self.assertEqual(production[production.index('--nodes')+1],'20')
        self.assertEqual(production[production.index('--ranks-per-node')+1],'all')
        self.assertEqual(production[production.index('--scope')+1],'deployment')
        shape=campaign.shape_for(20*92,float(production[production.index('--fft-mib-per-rank')+1]))
        self.assertLess(shape[0]*shape[1]*shape[2]*16*3,float(production[production.index('--max-checkpoint-gib')+1])*1024**3)
        self.assertFalse(any('--slurm-overlap' in c or '--oversubscribe' in c or 'prepare' in c for c in commands))
        serial=[c for c in calls if c['args'][0]=='test']
        self.assertEqual([c['args'][1] for c in serial],['fftw','hdf5','lapack'])
        self.assertTrue(all(c['cpu']=='7' for c in serial))
        self.assertEqual(commands[-1][:2],['osu','test'])
        self.assertTrue(any(c[0]=='summary' for c in commands))

    def test_partial_production_keeps_the_summary_but_never_starts_osu(self):
        result,calls=self.execute(True)
        self.assertNotEqual(result.returncode,0)
        commands=[v['args'] for v in calls]
        self.assertTrue(any(c[0]=='summary' for c in commands))
        self.assertFalse(any(c[:2]==['osu','test'] for c in commands))


if __name__=='__main__': unittest.main()
