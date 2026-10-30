import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import ssl
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('maintenance_merge',Path(__file__).with_name('patch_miniforge_trust.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
FIXTURE=json.loads((Path(__file__).parent/'fixtures/emudhra-incident-certificates.json').read_text())['certificates']


class IncidentKeyTests(unittest.TestCase):
 def test_public_key_fingerprints_match_disclosure_for_all_known_variants(self):
  self.assertEqual(len(FIXTURE),20)
  self.assertEqual(set(m.INCIDENT_PUBLIC_KEYS),{cert['spki_sha256'] for cert in FIXTURE})
  self.assertEqual(set(m.known_blocked_certificates()),{cert['sha256'] for cert in FIXTURE})
  for cert in FIXTURE:
   with self.subTest(cert=cert['sha256']):
    self.assertEqual(m.certificate_spki_sha256(cert['pem']),cert['spki_sha256'])
    self.assertIn(cert['sha256'],m.blocked_pem_entries(cert['pem']))
 def test_another_certificate_encoding_of_the_same_bad_key_is_still_blocked(self):
  for cert in FIXTURE:
   with self.subTest(cert=cert['sha256']):
    der=bytearray(ssl.PEM_cert_to_DER_cert(cert['pem']));der[-1]^=1
    variant=ssl.DER_cert_to_PEM_cert(bytes(der))
    fingerprint=m.hashlib.sha256(der).hexdigest().upper()
    self.assertNotEqual(fingerprint,cert['sha256'])
    self.assertIn(fingerprint,m.blocked_pem_entries(variant))
 def test_malformed_der_is_rejected_instead_of_bypassing_key_screening(self):
  for der in (b'',b'\x30\x80',b'\x30\x02\x30\x00',b'\x30\x82\x01',b'\x30\x01\x00'):
   with self.subTest(der=der),self.assertRaises(RuntimeError):m.certificate_spki_sha256(ssl.DER_cert_to_PEM_cert(der))


class SystemCAMergeTests(unittest.TestCase):
 def test_os_merge_filters_both_inputs_and_never_changes_the_os_source(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory).resolve();base=root/'miniforge';(base/'bin').mkdir(parents=True);(base/'bin/conda').touch();(base/'ssl').mkdir()
   blocked={row['sha256'] for row in FIXTURE}
   good=[ssl.DER_cert_to_PEM_cert(der) for der in ssl.create_default_context().get_ca_certs(binary_form=True) if m.hashlib.sha256(der).hexdigest().upper() not in blocked and m.certificate_spki_sha256(ssl.DER_cert_to_PEM_cert(der)) not in m.INCIDENT_PUBLIC_KEYS][:2]
   native=base/'ssl/cacert.pem';native.write_text(good[0]+FIXTURE[0]['pem']);native.chmod(0o640)
   alias=base/'ssl/cert.pem';alias.symlink_to('cacert.pem')
   source=root/'admin-system-ca.pem';source.write_text(good[1]+''.join(row['pem'] for row in FIXTURE));source.chmod(0o644)
   source_bytes=source.read_bytes();source_stat=source.stat()
   def run(apply,number):
    argv=['script',str(base),'--trust-only','--merge-system-ca','--log-dir',str(root/('logs-'+str(number)))]+(['--apply'] if apply else [])
    with patch.object(m.sys,'argv',argv),patch.object(m,'system_bundle',return_value=source),patch.object(m,'maintenance_gid',return_value=os.getegid()),patch.object(m.subprocess,'run',side_effect=AssertionError('No Conda, curl or package operation allowed')),contextlib.redirect_stdout(io.StringIO()):
     self.assertEqual(m.main(),0)
   before=native.read_bytes();run(False,0);self.assertEqual(native.read_bytes(),before)
   run(True,1)
   self.assertFalse(m.blocked_pem_entries(native.read_text()))
   self.assertEqual(set(dict(m.pem_entries(native.read_text()))),set(dict(m.pem_entries(''.join(good)))))
   self.assertTrue(alias.is_symlink());self.assertEqual(native.stat().st_mode&0o777,0o640)
   self.assertEqual(source.read_bytes(),source_bytes)
   self.assertEqual((source.stat().st_ino,source.stat().st_mode,source.stat().st_gid),(source_stat.st_ino,source_stat.st_mode,source_stat.st_gid))
   stat=native.stat();run(True,2)
   self.assertEqual((native.stat().st_ino,native.stat().st_mtime_ns),(stat.st_ino,stat.st_mtime_ns))
   source.write_text('-----BEGIN PRIVATE KEY-----\nnot-a-certificate\n-----END PRIVATE KEY-----\n')
   before=native.read_bytes()
   with self.assertRaisesRegex(RuntimeError,'plain CERTIFICATE'):run(True,3)
   self.assertEqual(native.read_bytes(),before)


if __name__=='__main__':unittest.main()
