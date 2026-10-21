"""Flag omissions, overwritten controls and unverifiable build evidence must be visible."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO/'production'),str(REPO/'scripts')]
import build_audit as audit
import campaign


class BuildAuditTests(unittest.TestCase):
    def test_actual_commands_catch_overrides_and_do_not_trust_a_flag_declaration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root/'flags.txt').write_text('CFLAGS="-O3 -fstack-protector-strong"')
            self.assertEqual(audit.compile_commands(root,root),( [],None))
            (root/'build.log').write_text('libtool: compile: /gcc/bin/gcc -O3 -fstack-protector-strong -D_FORTIFY_SOURCE=2 -c src.c -fno-stack-protector -O0 -o src.o\n')
            rows,_ = audit.compile_commands(root,root)
            failures = audit.check_commands(rows,{'CFLAGS':'-O3 -fstack-protector-strong -D_FORTIFY_SOURCE=2'})
            self.assertEqual({v['control'] for v in failures},{'stack','optimization'})
            (root/'compile_commands.json').write_text(json.dumps([{'file':'source.f90','arguments':['/gcc/bin/gfortran','-O3','-fstack-protector-strong','-fPIC','-c','source.f90']}]))
            rows,_ = audit.compile_commands(root,root)
            self.assertEqual(audit.check_commands(rows,{'FFLAGS':'-O3 -fstack-protector-strong -fPIC'}),[])

    def test_elf_requires_linker_controls_but_not_symbols_that_may_optimize_away(self):
        flags={'SHARED_LDFLAGS':'-Wl,-z,relro -Wl,-z,now -Wl,-z,noexecstack'}
        with patch.object(audit.subprocess,'check_output',return_value='Type: DYN\nGNU_RELRO\nGNU_STACK 0 0 0 0 0 RW 0\nFLAGS BIND_NOW\n'):
            row = audit.elf(Path('/lib.so'),flags)
            self.assertEqual(row['failures'],[])
            self.assertFalse(row['stack_canary_symbol']); self.assertEqual(row['fortified_symbols'],[])
        with patch.object(audit.subprocess,'check_output',return_value='Type: DYN\nGNU_STACK 0 0 RWE 0\n'):
            self.assertEqual(len(audit.elf(Path('/lib.so'),flags)['failures']),3)

    def test_a_system_compiler_cannot_pass_just_because_its_flags_match(self):
        rows=[{'source':'unit.c','compiler':'/system/bin/gcc','language':'CFLAGS'}]
        compilers={'CC':{'path':'/private/gcc/bin/gcc'}}
        self.assertEqual(len(audit.check_compilers(rows,compilers)),1)
        rows[0]['compiler']='/private/gcc/bin/gcc'
        self.assertEqual(audit.check_compilers(rows,compilers),[])
        rows[0]['compiler']='/private/mpi/bin/mpicc'
        self.assertEqual(audit.check_compilers(rows,compilers,Path('/private/mpi')),[])

    def test_missing_actual_compile_evidence_is_incomplete_even_with_valid_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); runner=root/'runner'; runner.mkdir()
            binary=root/'lib.so'; binary.write_bytes(b'\x7fELFfixture')
            flags={arm:{'CFLAGS':'-O3'} for arm in ('full','reference')}
            qualification={'flags':flags,'policy':{'disabled':{},'events':[]}}
            states={arm:{'identity':arm,'package':'fftw','arm':arm,'effective_profile':qualification,
                         'dependencies':{},'artifacts':{'lib.so':audit.sha(binary)}} for arm in flags}
            driver=types.SimpleNamespace(ROOT=root,HERE=runner,require_setup=lambda **kw:None,
                read=lambda p:qualification,save=lambda p,v:p.write_text(json.dumps(v)),
                get_flags=lambda arm:flags[arm],verify_state=lambda name:states[name.rsplit('-',1)[1]],
                paths=lambda *a:(root/'build',root/'install'))
            with patch.object(audit,'PACKAGES',('fftw',)),patch.object(audit,'compiler_inventory',return_value={}),patch.object(audit,'elf',return_value={'failures':[]}),contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(RuntimeError,'did not pass'): audit.audit(driver,[])
            value=json.loads(next((root/'results/build-audit').glob('*/audit.json')).read_text())
            self.assertEqual(value['status'],'incomplete')
            self.assertEqual(value['historical_verification'],'not_supplied')
            safe=next((root/'results/build-audit').glob('*/shareable-summary.json')).read_text()
            self.assertNotIn(str(root),safe)
            self.assertIn('compatibility_reductions',safe)

    def test_reframe_exposes_a_stable_campaign_pointer_to_batch_jobs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); pointer=root/'batch-pointer.json'
            driver=types.SimpleNamespace(ROOT=root,HERE=root/'runner',check_reframe=lambda:Path('/reframe'))
            def run(cmd,env):
                Path(env['TRIAL_PRODUCTION_POINTER']).write_text(json.dumps({'campaign':'/underlying/result'}))
                return types.SimpleNamespace(returncode=0)
            with patch.object(campaign.subprocess,'run',side_effect=run),contextlib.redirect_stdout(io.StringIO()):
                campaign.run_reframe(driver,['test','--reframe'],types.SimpleNamespace(result_pointer=pointer),'osu')
            self.assertEqual(json.loads(pointer.read_text()),{'campaign':'/underlying/result'})


if __name__=='__main__': unittest.main()
