"""Check distro-specific system CA discovery without touching the host trust store."""
import importlib.util
import json
from pathlib import Path
import ssl
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('maintenance_locations',Path(__file__).with_name('patch_miniforge_trust.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class SystemCALocationTests(unittest.TestCase):
 def discover(self,root):
  with patch.object(m,'Path',side_effect=lambda value:root/str(value).lstrip('/')):
   return m.system_bundle()

 def test_rhel_suse_and_debian_layouts_are_independently_discovered_and_filtered(self):
  bad=json.loads((Path(__file__).parent/'fixtures/emudhra-incident-certificates.json').read_text())['certificates'][0]['pem']
  good=next(ssl.DER_cert_to_PEM_cert(cert) for cert in ssl.create_default_context().get_ca_certs(binary_form=True)
            if not m.blocked_pem_entries(ssl.DER_cert_to_PEM_cert(cert)))
  paths=(('rhel-modern','/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem'),
         ('rhel-legacy','/etc/pki/tls/certs/ca-bundle.crt'),
         ('suse-alias','/etc/ssl/ca-bundle.pem'),
         ('suse-generated','/var/lib/ca-certificates/ca-bundle.pem'),
         ('debian','/etc/ssl/certs/ca-certificates.crt'))
  for distro,location in paths:
   with self.subTest(distro=distro),tempfile.TemporaryDirectory() as directory:
    root=Path(directory).resolve();source=root/location.lstrip('/');source.parent.mkdir(parents=True)
    source.write_text(good+bad);before=source.read_bytes();original=source.stat()
    selected=self.discover(root);self.assertEqual(selected,source)
    output,removed=m.filtered_bundle([selected]);self.assertTrue(removed);self.assertFalse(m.blocked_pem_entries(output))
    self.assertEqual(set(dict(m.pem_entries(output))),set(dict(m.pem_entries(good))))
    self.assertEqual(source.read_bytes(),before)
    self.assertEqual((source.stat().st_ino,source.stat().st_mtime_ns,source.stat().st_mode),(original.st_ino,original.st_mtime_ns,original.st_mode))

 def test_rhel_extracted_pem_precedes_the_legacy_store_format(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory).resolve()
   expected=root/'etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem';expected.parent.mkdir(parents=True);expected.touch()
   legacy=root/'etc/pki/tls/certs/ca-bundle.crt';legacy.parent.mkdir(parents=True)
   legacy.write_text('-----BEGIN TRUSTED CERTIFICATE-----\nunsupported AUX data\n-----END TRUSTED CERTIFICATE-----\n')
   self.assertEqual(self.discover(root),expected)

 def test_suse_alias_resolves_to_generated_file_without_writing_it(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory).resolve();source=root/'var/lib/ca-certificates/ca-bundle.pem';source.parent.mkdir(parents=True);source.write_text('untouched')
   alias=root/'etc/ssl/ca-bundle.pem';alias.parent.mkdir(parents=True);alias.symlink_to(source)
   self.assertEqual(self.discover(root),source);self.assertTrue(alias.is_symlink());self.assertEqual(source.read_text(),'untouched')

 def test_dangling_alias_is_skipped_and_no_os_source_fails_explicitly(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory).resolve();legacy=root/'etc/pki/tls/certs/ca-bundle.crt';legacy.parent.mkdir(parents=True);legacy.symlink_to(root/'missing')
   with self.assertRaisesRegex(RuntimeError,'Cannot locate host PEM bundle'):self.discover(root)
   suse=root/'var/lib/ca-certificates/ca-bundle.pem';suse.parent.mkdir(parents=True);suse.touch()
   self.assertEqual(self.discover(root),suse)


if __name__=='__main__':unittest.main()
