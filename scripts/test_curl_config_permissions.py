import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from http.server import HTTPServer, BaseHTTPRequestHandler

spec=importlib.util.spec_from_file_location('maintenance_curl_config',Path(__file__).with_name('patch_miniforge_trust.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class LinkGroupTests(unittest.TestCase):
 def test_link_groups_change_without_changing_external_targets(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory).resolve();base=root/'base';base.mkdir();base.chmod(0o2775)
   external=root/'admin.pem';external.write_text('untouched certificate');external.chmod(0o600)
   folder=root/'admin-directory';folder.mkdir();(folder/'keep').write_text('untouched')
   links=[base/'cert.pem',base/'linked-dir'];links[0].symlink_to(external);links[1].symlink_to(folder,target_is_directory=True)
   wanted=os.getegid();original=Path.lstat;before=external.stat();stats={}
   def lstat(path):
    result=original(path)
    if path in links:
     values=list(result);values[5]=wanted+10000;return os.stat_result(values)
    return result
   with patch.object(m,'maintenance_gid',return_value=wanted),patch.object(Path,'lstat',lstat),patch.object(os,'lchown') as chgrp:
    m.public_permissions(base,base,True,lambda message:None,stats=stats)
   self.assertEqual({call.args for call in chgrp.call_args_list},{(str(path),-1,wanted) for path in links})
   self.assertEqual((external.stat().st_gid,external.stat().st_mode,external.stat().st_ino),(before.st_gid,before.st_mode,before.st_ino))
   self.assertEqual(external.read_text(),'untouched certificate');self.assertEqual((folder/'keep').read_text(),'untouched')
   self.assertTrue(all(path.is_symlink() for path in links))
 def test_permissions_only_preserves_merged_pem_contents_without_package_commands(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);base=root/'base';base.mkdir();pem=base/'cert.pem';pem.write_text('already merged OS certificates');pem.chmod(0o600)
   args=SimpleNamespace(log_dir=root/'logs',apply=True,verbose=False)
   with patch.object(m,'maintenance_gid',return_value=os.getegid()),patch.object(m.subprocess,'run') as run,contextlib.redirect_stdout(io.StringIO()):
    self.assertEqual(m.permissions_only(args,base),0)
   run.assert_not_called();self.assertEqual(pem.read_text(),'already merged OS certificates')
   self.assertEqual(pem.stat().st_mode&0o777,0o664)


class CurlReadOnlyCheckTests(unittest.TestCase):
 def test_cli_check_needs_no_shared_maintenance_access(self):
  with patch.object(m.sys,'argv',['script','--check-curl','--curl-url','https://needed.example/']),patch.object(m,'find_base',return_value=Path('/base')),patch.object(m,'check_curl',return_value=0) as check,patch.object(m,'maintenance_gid') as group,patch.object(m,'maintainable') as write:
   self.assertEqual(m.main(),0)
  check.assert_called_once();group.assert_not_called();write.assert_not_called()
 def test_custom_url_recheck_changes_no_base_files_or_packages(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);base=root/'base';base.mkdir();pem=base/'cert.pem';pem.write_text('existing merged CA bundle')
   args=SimpleNamespace(log_dir=root/'check',curl_url='https://needed.example/path',channel=[])
   calls=[]
   def fake(command,**kwargs):
    calls.append(command)
    self.assertEqual(command[0],str(base/'bin/python'))
    self.assertIn(command[4],(m.CURL_PROBE,m.CURL_HTTPS_PROBE))
    return subprocess.CompletedProcess(command,0,json.dumps({'http_status':'200'}),'')
   with patch.object(m.subprocess,'run',side_effect=fake),contextlib.redirect_stdout(io.StringIO()):
    self.assertEqual(m.check_curl(args,base,os.environ.copy()),0)
   self.assertEqual(pem.read_text(),'existing merged CA bundle');self.assertEqual(len(calls),2)
   self.assertEqual(calls[-1][-2:],[args.curl_url,'direct'])


@unittest.skipUnless(shutil.which('openssl') and Path('/usr/bin/curl').is_file(),'Local OpenSSL and curl are required')
class CurlConfigTLSChecks(unittest.TestCase):
 def test_normal_curlrc_ca_is_honored_but_insecure_is_not(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory).resolve();base=root/'base';home=root/'curl-home'
   (base/'bin').mkdir(parents=True);(base/'conda-meta').mkdir();home.mkdir()
   config=root/'cert.cnf';key=root/'key.pem';cert=root/'cert.pem'
   config.write_text('[req]\nprompt=no\ndistinguished_name=dn\nx509_extensions=v3\n[dn]\nCN=localhost\n[v3]\nsubjectAltName=DNS:localhost\nbasicConstraints=critical,CA:TRUE\nkeyUsage=digitalSignature,keyEncipherment,keyCertSign\n')
   subprocess.run([shutil.which('openssl'),'req','-new','-x509','-newkey','rsa:2048','-nodes','-days','1','-config',str(config),'-keyout',str(key),'-out',str(cert)],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
   # Model a Conda binary layout while forwarding HTTPS to a real curl client.
   binary=base/'bin/curl';binary.write_text('#!/bin/sh\nif [ "$1" = "-q" ] && [ "$2" = "--version" ]; then\n  printf "%s\\n" "curl 8.23.0 (test) libcurl/8.23.0 OpenSSL/3"\n  exit 0\nfi\nexec /usr/bin/curl "$@"\n');binary.chmod(0o755)
   for name in ('curl','libcurl'):(base/'conda-meta'/(name+'.json')).write_text(json.dumps({'name':name,'version':'8.23.0','build':'0'}))
   class Handler(BaseHTTPRequestHandler):
    def do_HEAD(self):self.send_response(200);self.end_headers()
    def log_message(self,*args):pass
   try:server=HTTPServer(('127.0.0.1',0),Handler)
   except PermissionError as exc:self.skipTest('Local socket unavailable: '+str(exc))
   context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(str(cert),str(key));server.socket=context.wrap_socket(server.socket,server_side=True)
   thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
   url='https://localhost:%d/'%server.server_port
   env=dict(os.environ,CURL_HOME=str(home),PATH=str(base/'bin')+os.pathsep+os.environ['PATH'],NO_PROXY='localhost,127.0.0.1',no_proxy='localhost,127.0.0.1')
   for name in ('CURL_CA_BUNDLE','SSL_CERT_FILE','SSL_CERT_DIR'):env.pop(name,None)
   try:
    (home/'.curlrc').write_text('cacert = "'+str(cert)+'"\n')
    with patch.dict(os.environ,env,clear=True),patch.object(m.sys,'prefix',str(base)),patch.object(m.sys,'argv',['probe',url]),contextlib.redirect_stdout(io.StringIO()) as output:
     exec(m.CURL_HTTPS_PROBE,{})
    self.assertEqual(json.loads(output.getvalue())['http_status'],'200')
    # A successful manual request with insecure enabled must not weaken our check.
    (home/'.curlrc').write_text('insecure\n')
    with patch.dict(os.environ,env,clear=True),patch.object(m.sys,'prefix',str(base)),patch.object(m.sys,'argv',['probe',url]):
     with self.assertRaisesRegex(RuntimeError,'certificate|curl.*60'):exec(m.CURL_HTTPS_PROBE,{})
   finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':unittest.main()
