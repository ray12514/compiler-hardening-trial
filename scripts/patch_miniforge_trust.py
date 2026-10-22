#!/usr/bin/env python3
"""CSE Miniforge certificate maintenance, revision 4 (2026-10-22).

Python 3.8+, standard library. Run as a maintenance account, not root.
  python3 patch_miniforge_trust.py                       # preview loaded install
  python3 patch_miniforge_trust.py /path/to/miniforge     # explicit install
  python3 patch_miniforge_trust.py --apply               # apply, normal channels
  python3 patch_miniforge_trust.py --apply --offline     # approved cached packages
  python3 patch_miniforge_trust.py --apply --upgrade-conda

No test-site connections, connectivity probes, remote execution or OS writes.
Preview is local-only: inventory, CA inspection, ownership and permissions.
Apply enforces conda-forge with --override-channels and strict channel priority.
There is no PyPI/pip-install fallback. External conda plugins are disabled for
maintenance subprocesses so conda-pypi cannot introduce a PyPI source.
--offline forbids network package retrieval; required packages must be cached or
available in the configured conda-forge mirror/cache. No installer replacement is required.
Run once per distinct shared installation on each system; it does not SSH to hosts.

Discovery: CONDA_EXE, conda on PATH, or explicit positional path. Uses that conda's
base, env list, immediate envs-dir children and --include paths. Group maintenance
checks primary/supplementary memberships AND effective prefix/conda-meta write
access. It does not search other users' homes. --scan-root ROOT optionally locates
unregistered prefixes under a site-owned software root. Repeated --exclude PREFIX
also excludes its descendants. All selected eligible prefixes are treated as shared.

Default package targets: existing ca-certificates>=2026.10.19 (conda-forge),
certifi>=2026.10.19, pip>=26.2.2, uv>=0.13.4, and sigstore>=4.5.1 where
installed through conda. --upgrade-conda also requests
conda>=26.9.4 where installed. Related mamba/solver packages are requested together
when installed. Python and non-management packages are pinned to version+build.
If pins or the mirror block the remediation, report failure instead of upgrading
Python/scientific packages. --freeze-installed and the classic solver are used.
Python <3.11 with conda-forge certifi may need a reviewed backport or replacement
prefix. Existing conda may be retained per the conda maintainers' CA-only guidance.
Outdated pip-managed tools are reported for reviewed migration to conda-forge,
without automatically overwriting pip-owned files. If sigstore is installed,
an offline `python -I -m sigstore --help` smoke check reports startup failures.
A fixed package version does not establish that an unrelated crash is resolved.

A CSE-owned bundle at BASE/etc/cse-trust/ca-bundle.pem is built locally from the
selected existing site bundle, preserving all certificates except four exact
incident-root SHA256 fingerprints. This is an INTERIM incident mitigation, not a
complete refresh of Mozilla/public roots. Removing broad roots (especially AAA)
can break legitimate certificates chaining to them. It is confined to CSE files.
The source is --ca-bundle, otherwise configured ssl_verify when it is a filename,
then REQUESTS_CA_BUNDLE/CURL_CA_BUNDLE/SSL_CERT_FILE, then OS store for truststore,
otherwise base/ssl/cacert.pem or cert.pem, then OS fallback. --extra-ca PATH adds
explicit organizational roots. The source must be plain PEM certificates; trust
policy/AUX/private-key/other PEM blocks are rejected rather than losing policy.
An unavailable configured source fails closed. No CAs are removed from /etc.
Replacing the source later with a corrected vendor/site bundle rebuilds this copy.

Conda SSL configuration and conda activation variables are set for updated prefixes
so the CSE bundle is used, including SSL_CERT_DIR pointing to a dedicated empty
CA directory. Existing configuration/state is saved privately before modification.
A shell snippet BASE/etc/cse-trust/use-ca.sh is emitted for the current shell or
site modulefile to source; existing sessions must reload it or reactivate. The
script cannot edit an unknown Tcl/Lua modulefile or another user's .condarc.
Activation variables override previous values only in managed environments and
conda restores activation-managed variables on deactivation. Review other apps
and independently configured bundles; nothing here changes proxy upstream trust.

Permission policy: the exact lowercase group cse is required. Its numeric GID
is resolved locally on each host; the current account must be a member. Shared
directories become cse:2775, ordinary files cse:0664, existing executables
cse:0775. UID ownership is preserved. Membership in other groups is still used
to discover maintainable prefixes, but never selects the output group. This
policy applies to eligible selected prefixes, not arbitrary parent directories.
Symlinks are not followed. Hardlinks are broken before group/mode changes so
other environments and caches keep their metadata. Known private/secret paths
and privileged files are excluded; foreign-owned files needing changes and
extended ACLs are reported for owner/admin review. Group membership does not
allow chmod/chgrp of another owner's files. Parent traversal blockers are
reported, not widened. Unknown credentials cannot be detected: exclude private
prefixes. Package-cache contents and unrelated nested prefixes are not changed.

Logs and configuration backups default to a persistent private directory in your
home (or --log-dir), outside managed trees. They are NOT a package/filesystem
snapshot. Take your normal snapshot and stop concurrent jobs/package updates.
Interrupted/failed transactions can leave partial work; summaries distinguish it.
No claim of exploitation, end-to-end protection, or proxy remediation is made.
--chains-dir optionally checks approved local incident chain files offline using
OpenSSL 3; no test material is downloaded. Only issuer/distrust failures qualify.
Absence of known root fingerprints is screening, not full chain verification.

Sources:
https://conda.org/blog/2026-10-21-emudhra-security-updates/
https://discuss.python.org/t/109576
https://emudhra.we-have-a-problem.com/roots.json
https://docs.conda.io/projects/conda/en/24.11.x/commands/install.html
https://p11-glue.github.io/p11-glue/p11-kit/manual/trust.html
"""
import argparse
import datetime
import fcntl
import grp
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import ssl
import stat
import subprocess
import sys
import tempfile
import traceback

MINIMUM = {'ca-certificates':'2026.10.19', 'certifi':'2026.10.19',
           'pip':'26.2.2', 'uv':'0.13.4', 'sigstore':'4.5.1'}
ROOTS = {
 '7DD78D5F4F13459A83DFF9ABBBA62EDBAF6F2D102BF257FD712F4D9F2746ED8D': 'emSign Root TLS CA - G3',
 'F2EDAAFF3D9B701FB4D14C9F285F8C0BAD90FC3BCC1FA07D47F4718EDABA34A5': 'emSign Root CS CA - G3',
 'D7A7A0FB5D7E2731D771E9484EBCDEF71D5F0C3E0A2948782BC83EE0EA699EF4': 'AAA Certificate Services',
 '86A1ECBA089C4A8D3BBE2734C612BA341D813E043CF9E8A862CD5C57A36BBE6B': 'emSign ECC Root CA - G3',
}
MANAGERS = {'mamba','libmamba','libmambapy','conda-libmamba-solver','conda-pypi'}
# Only this management/runtime dependency set may move without a separate review.
MANAGEMENT_DEPS = MANAGERS | {'conda','conda-self','conda-package-handling',
 'conda-package-streaming','archspec','boltons','brotli-python','c-ares','certifi',
 'ca-certificates','cffi','charset-normalizer','cryptography','distro','fmt',
 'frozendict','h2','hpack','hyperframe','idna','jsonpatch','jsonpointer','libarchive',
 'libcurl','libnghttp2','libsolv','libssh2','libxml2','lz4-c','lzo','menuinst',
 'msgpack-python','nlohmann_json','openssl','packaging','pcre2','platformdirs',
 'pluggy','pycosat','pycparser','pysocks','python_abi','reproc','reproc-cpp',
 'requests','ruamel.yaml','ruamel.yaml.clib','simdjson','tqdm','truststore',
 'typing_extensions','urllib3','yaml-cpp','zstandard','zstd',
 'annotated-types','betterproto','email-validator','exceptiongroup','id',
 'dnspython','httpcore','httpx','h11','anyio','sniffio','pydantic','pydantic-core',
 'pyjwt','pyopenssl','rich','markdown-it-py','mdurl','pygments','rfc3161-client',
 'securesystemslib','sigstore-models','sigstore-protobuf-specs','sigstore-rekor-types',
 'tuf','typing-inspection','importlib-metadata','zipp'}
CHANNEL_ARGS = ['--override-channels','--channel','conda-forge','--strict-channel-priority']
MAINTENANCE_GROUP = 'cse'

SECRETS = {'.condarc','.netrc','.pypirc','.ssh','.aws','.azure','.config','.git',
           '.env','credentials','tokens','secrets'}

def version(v):
    # Security minimums are stable dotted numeric versions; prereleases fail closed.
    parts = str(v).split('.')
    if not all(p.isdigit() for p in parts):
        raise RuntimeError('Non-stable version needs manual review: ' + str(v))
    return tuple(map(int, parts))


def owned(p):
    return p.stat().st_uid == os.geteuid() and os.access(str(p), os.W_OK | os.X_OK)


def groups():
    return set(os.getgroups()) | {os.getegid()}


def maintainable(p):
    st = p.stat()
    identity = st.st_uid == os.geteuid() or (st.st_gid in groups() and st.st_mode & stat.S_IWGRP)
    return bool(identity and os.access(str(p), os.W_OK | os.X_OK))


def system_bundle():
    for p in ('/etc/pki/tls/certs/ca-bundle.crt', '/etc/ssl/certs/ca-certificates.crt',
              '/etc/ssl/ca-bundle.pem', '/var/lib/ca-certificates/ca-bundle.pem'):
        if Path(p).is_file():
            return Path(p).resolve()
    raise RuntimeError('Cannot locate host PEM bundle; supply --ca-bundle PATH')


def maintenance_gid():
    try:
        gid = grp.getgrnam(MAINTENANCE_GROUP).gr_gid
    except KeyError:
        raise RuntimeError("Required group 'cse' does not exist on this host")
    if gid not in groups():
        raise RuntimeError("Current account must be a member of group 'cse'; check your login's group membership")
    return gid


def public_mode(mode, is_dir):
    if is_dir:
        return 0o2775 | (mode & stat.S_ISVTX)
    return 0o775 if mode & 0o111 else 0o664


def secret(p):
    return p.name in SECRETS or p.name.endswith(('.key', '.p12', '.pfx'))


def public_permissions(prefix, base, apply, say):
    problems, changed = [], 0
    shared_gid = maintenance_gid()
    def visit(p):
        nonlocal changed
        st = p.lstat()
        if stat.S_ISLNK(st.st_mode):
            return
        if not (stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode)):
            return
        if hasattr(os, 'listxattr') and 'system.posix_acl_access' in os.listxattr(str(p)):
            problems.append('Extended ACL needs review: ' + str(p)); return
        old = stat.S_IMODE(st.st_mode)
        if stat.S_ISREG(st.st_mode) and old & (stat.S_ISUID | stat.S_ISGID):
            problems.append('Privileged file needs manual review: ' + str(p)); return
        new = public_mode(old, stat.S_ISDIR(st.st_mode))
        desired_gid = shared_gid
        if old == new and desired_gid == st.st_gid:
            return
        if st.st_uid != os.geteuid():
            # A group maintainer can replace files but cannot chmod another UID's files.
            # Do not take ownership by replacing them merely for permissions.
            problems.append("Owner must set group cse and required permissions: " + str(p)); return
        changed += 1
        if apply:
            if stat.S_ISREG(st.st_mode) and st.st_nlink > 1:
                fd, tmp = tempfile.mkstemp(prefix='.trust-mode-', dir=str(p.parent))
                os.close(fd)
                try:
                    shutil.copy2(str(p), tmp)
                    os.chown(tmp, -1, desired_gid)
                    os.chmod(tmp, new)
                    os.replace(tmp, str(p))
                finally:
                    if os.path.exists(tmp): os.unlink(tmp)
            else:
                if desired_gid != st.st_gid: os.chown(str(p), -1, desired_gid)
                os.chmod(str(p), new)
    def walk_error(exc):
        problems.append('Unreadable subtree: ' + str(exc))
    for root, dirs, files in os.walk(str(prefix), followlinks=False, onerror=walk_error):
        root = Path(root)
        visit(root)
        keep = []
        for name in dirs:
            p = root / name
            if secret(p):
                say('Preserving private-path permissions: ' + str(p)); continue
            if p.is_symlink(): continue
            if prefix == base and name in ('pkgs', 'envs') and root == base:
                visit(p); continue
            if (p / 'conda-meta/history').is_file():
                continue
            keep.append(name)
        dirs[:] = keep
        for name in files:
            p = root / name
            if secret(p):
                say('Preserving private-path permissions: ' + str(p)); continue
            visit(p)
    for p in prefix.parents:
        if not p.stat().st_mode & stat.S_IXOTH:
            problems.append('Parent lacks other-traverse bit (ACL may differ): ' + str(p))
    say('Permissions %s: %d paths' % ('changed' if apply else 'would change', changed))
    return problems



AUDIT = r'''
import sys, json, ssl, importlib.util
from importlib import metadata
d = {'python': list(sys.version_info[:3]), 'packages': {}, 'bundles': {}}
for name in ('pip','certifi','uv','sigstore','pixi'):
    try: d['packages'][name] = metadata.version(name)
    except metadata.PackageNotFoundError: pass
for name in ('certifi','pip._vendor.certifi'):
    try:
        m = __import__(name, fromlist=['where'])
        d['bundles'][name] = m.where()
    except (ImportError, AttributeError): pass
p = ssl.get_default_verify_paths()
if p.cafile: d['bundles']['openssl'] = p.cafile
print(json.dumps(d))
'''


def pem_entries(data):
    blocks = re.findall(r'-----BEGIN ([A-Z0-9 ]+)-----.*?-----END \1-----', data, re.S)
    if not blocks or any(label != 'CERTIFICATE' for label in blocks):
        raise RuntimeError('Source must contain plain CERTIFICATE PEM blocks only; use an approved PEM bundle')
    result = []
    for pem in re.findall(r'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----', data, re.S):
        der = ssl.PEM_cert_to_DER_cert(pem)
        result.append((hashlib.sha256(der).hexdigest().upper(), pem + '\n'))
    return result


def filtered_bundle(paths):
    kept, removed = {}, set()
    for p in paths:
        for fingerprint, pem in pem_entries(Path(p).read_text()):
            if fingerprint in ROOTS:
                removed.add(ROOTS[fingerprint])
            else:
                kept[fingerprint] = pem
    if not kept:
        raise RuntimeError('No certificates would remain in the CSE bundle')
    output = ''.join(kept.values())
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.load_verify_locations(cadata=output)  # parse only; no connection
    return output, sorted(removed)


def atomic_write(p, data, mode=0o644):
    p = Path(p)
    fd, tmp = tempfile.mkstemp(prefix='.cse-trust-', dir=str(p.parent))
    try:
        with os.fdopen(fd, 'w') as f: f.write(data)
        os.chown(tmp, -1, maintenance_gid())
        os.chmod(tmp, public_mode(mode, False))
        os.replace(tmp, str(p))
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def records(prefix):
    out = {}
    for f in (prefix / 'conda-meta').glob('*.json'):
        r = json.loads(f.read_text()); out[r['name']] = r
    return out


def safe_environment():
    env = os.environ.copy()
    for k in ('PYTHONPATH','PYTHONHOME','LD_PRELOAD','LD_LIBRARY_PATH',
              'OPENSSL_CONF','OPENSSL_MODULES','OPENSSL_ENGINES',
              'SSL_CERT_DIR','PIP_TRUSTED_HOST'):
        env.pop(k, None)
    env['CONDA_OFFLINE'] = 'true'
    env['PIP_DISABLE_PIP_VERSION_CHECK'] = '1'
    env['PIP_NO_INDEX'] = '1'
    env['CONDA_NO_PLUGINS'] = 'true'
    return env


def capture(cmd, env):
    r = subprocess.run(list(map(str,cmd)), env=env, text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if r.returncode:
        raise RuntimeError('Local discovery command failed: ' + r.stderr[-1500:])
    return r.stdout


def find_base(explicit, env):
    if explicit:
        base = explicit.expanduser().resolve(strict=True)
    else:
        executable = os.environ.get('CONDA_EXE') or shutil.which('conda')
        if not executable:
            raise RuntimeError('Load your CSE Miniforge module or pass /path/to/miniforge')
        base = Path(capture([executable,'info','--base'],env).strip()).resolve(strict=True)
    if not (base/'bin/conda').is_file():
        raise RuntimeError('Not a Miniforge/conda base: ' + str(base))
    return base


def choose_source(args, config, base):
    if args.ca_bundle: return args.ca_bundle.expanduser().resolve(strict=True)
    setting = config.get('ssl_verify', True)
    if isinstance(setting,str) and setting not in ('truststore','true','false'):
        return Path(os.path.expandvars(setting)).expanduser().resolve(strict=True)
    for k in ('REQUESTS_CA_BUNDLE','CURL_CA_BUNDLE','SSL_CERT_FILE'):
        value = os.environ.get(k)
        if value: return Path(value).expanduser().resolve(strict=True)
    if setting == 'truststore': return system_bundle()
    for rel in ('ssl/cacert.pem','ssl/cert.pem'):
        if (base/rel).is_file(): return (base/rel).resolve()
    return system_bundle()


def discover(base, conda, env, includes, scans, excludes):
    inventory = json.loads(capture([conda,'env','list','--json'],env))
    paths = {base} | {Path(p).resolve() for p in inventory['envs']} | {p.expanduser().resolve() for p in includes}
    if (base/'envs').is_dir():
        paths |= {p.resolve() for p in (base/'envs').iterdir() if (p/'conda-meta/history').is_file()}
    for scan in scans:
        scan = scan.expanduser().resolve(strict=True)
        for root, dirs, files in os.walk(str(scan), followlinks=False):
            root = Path(root)
            if (root/'conda-meta/history').is_file(): paths.add(root.resolve())
            dirs[:] = [d for d in dirs if d not in ('pkgs','conda-meta','.git') and not (root/d).is_symlink()]
    exclusions = [p.expanduser().resolve() for p in excludes]
    return sorted([p for p in paths if not any(p == x or x in p.parents for x in exclusions)],
                  key=lambda p:(p != base,str(p)))


def plan_specs(meta, upgrade_conda):
    targets = set(meta) & (set(MINIMUM) | MANAGERS)
    if upgrade_conda and 'conda' in meta: targets.add('conda')
    specs = [n + '>=' + MINIMUM[n] if n in MINIMUM else
             ('conda>=26.9.4' if n == 'conda' else n) for n in sorted(targets)]
    allowed = targets | MANAGEMENT_DEPS
    if not upgrade_conda: allowed -= {'conda','conda-self'}
    # Scientific packages, Python and ABI always keep exact installed builds.
    allowed -= {'python','python_abi'}
    for n,r in sorted(meta.items()):
        if n not in allowed:
            specs.append(n + '=' + r['version'] + '=' + r['build'])
    return targets, allowed, specs


def check_plan(plan, allowed):
    if plan.get('success') is False: raise RuntimeError('Conda solver reported failure')
    actions = plan.get('actions',{})
    linked = {r['name'] for r in actions.get('LINK',[])}
    unlinked = {r['name'] for r in actions.get('UNLINK',[])}
    if (linked | unlinked) - allowed:
        raise RuntimeError('Rejected unrelated package changes: ' + ', '.join(sorted((linked|unlinked)-allowed)))
    if unlinked - linked:
        raise RuntimeError('Rejected package removal without replacement: ' + ', '.join(sorted(unlinked-linked)))
    return sorted(linked | unlinked)


def verify_chains(openssl, bundle, chains, env, run):
    files = sorted(chains.glob('*.pem'))
    if not files: raise RuntimeError('--chains-dir has no PEM test chains')
    if not capture([openssl,'version'],env).startswith('OpenSSL 3.'):
        raise RuntimeError('Offline chain verification requires OpenSSL 3')
    for p in files:
        r = run([openssl,'verify','-show_chain','-no-CApath','-no-CAstore',
                 '-purpose','sslserver','-CAfile',bundle,'-untrusted',p,p], allow_failure=True)
        if r.returncode == 0: raise RuntimeError('UNSAFE: accepted local test chain ' + p.name)
        # Reject expired/malformed/mixed errors instead of treating all failures as protection.
        codes = {int(c) for c in re.findall(r'error (\d+) at', r.stdout+r.stderr)}
        if not codes or not codes <= {20,21,23,27}:
            raise RuntimeError('INCONCLUSIVE local chain check: ' + p.name)


def sigstore_startup(py, env, log):
    try:
        r = subprocess.run([str(py),'-I','-m','sigstore','--help'], env=env,
                           text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=30)
    except subprocess.TimeoutExpired:
        return 'sigstore startup timed out after 30 seconds'
    log.write(r.stdout+r.stderr)
    if r.returncode:
        return 'sigstore startup failed (exit %d); see run.log for traceback/signal' % r.returncode
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('miniforge', nargs='?', type=Path)
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--offline', action='store_true',help='Apply using cache/file channels; never retrieve online')
    ap.add_argument('--upgrade-conda',action='store_true',help='Also upgrade installed conda; default retain its version/build')
    ap.add_argument('--ca-bundle',type=Path,help='Source site PEM; default detect from conda/current configuration')
    ap.add_argument('--extra-ca',type=Path,action='append',default=[])
    ap.add_argument('--include',type=Path,action='append',default=[])
    ap.add_argument('--exclude',type=Path,action='append',default=[])
    ap.add_argument('--scan-root',type=Path,action='append',default=[])
    ap.add_argument('--chains-dir',type=Path,help='Approved local incident chain directory; no downloads')
    ap.add_argument('--log-dir',type=Path)
    args = ap.parse_args()
    if os.geteuid() == 0: ap.error('Run as the software maintenance account, not root')
    cse_gid = maintenance_gid()  # validate before any deployment changes
    os.umask(0o002)
    env = safe_environment()
    base = find_base(args.miniforge,env); conda = base/'bin/conda'
    if not maintainable(base): raise RuntimeError('No user/group maintenance access to base')
    config = json.loads(capture([conda,'config','--show','ssl_verify','--json'],env))
    source = choose_source(args,config,base)
    bundle_text, removed = filtered_bundle([source] + args.extra_ca)
    prefixes = discover(base,conda,env,args.include,args.scan_root,args.exclude)
    logdir = (args.log_dir or Path.home()/'.cse-trust-logs'/datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')).expanduser().resolve()
    if any(logdir == p or p in logdir.parents for p in prefixes):
        raise RuntimeError('Logs must be outside all selected environment trees')
    logdir.mkdir(mode=0o700,parents=True,exist_ok=False)
    os.chmod(str(logdir),0o700)
    log = open(str(logdir/'run.log'),'w',buffering=1)
    def say(s): print(s,flush=True);log.write(s+'\n')
    say('Mode: '+('APPLY' if args.apply else 'LOCAL PREVIEW; no network operations'))
    say('Package source: conda-forge ONLY; external plugins disabled; no PyPI fallback')
    say('Base: '+str(base)); say('Source CA: '+str(source));say('Private logs: '+str(logdir))
    say('Current UID/groups: %s / %s' % (os.geteuid(),','.join(map(str,sorted(groups())))))
    say('Shared permissions target: cse (GID %d); directories 2775, files 0664, executables 0775' % cse_gid)
    say('Roots removed from CSE copy: '+(', '.join(removed) or 'none of the four matched'))
    say('This is local mitigation, not evidence of proxy remediation or a full trust-store refresh.')
    def run(cmd, allow_failure=False):
        say('$ '+shlex.join(map(str,cmd)))
        r = subprocess.run(list(map(str,cmd)),env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        log.write(r.stdout+r.stderr)
        if r.returncode and not allow_failure: raise RuntimeError('Command failed; see private run.log')
        return r
    def runjson(cmd): return json.loads(run(cmd).stdout)
    trustdir = base/'etc/cse-trust'; bundle = trustdir/'ca-bundle.pem'; empty = trustdir/'empty-ca-dir'
    values = {k:str(bundle) for k in ('CONDA_SSL_VERIFY','REQUESTS_CA_BUNDLE','SSL_CERT_FILE','CURL_CA_BUNDLE','PIP_CERT')}
    values['SSL_CERT_DIR'] = str(empty)
    results = []
    lockfile = None
    if args.apply:
        trustdir.mkdir(mode=0o755,parents=True,exist_ok=True)
        if not maintainable(trustdir): raise RuntimeError('No maintenance access to CSE trust directory')
        if trustdir.stat().st_uid == os.geteuid():
            os.chown(str(trustdir), -1, cse_gid); os.chmod(str(trustdir), 0o2775)
        lockfile = open(str(trustdir/'maintenance.lock'),'a')
        fcntl.flock(lockfile.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        if os.fstat(lockfile.fileno()).st_uid == os.geteuid():
            os.fchown(lockfile.fileno(), -1, cse_gid); os.fchmod(lockfile.fileno(), 0o664)
        marker = trustdir/'managed-by-patch-miniforge-trust'
        if bundle.exists() and not marker.is_file(): raise RuntimeError('Refusing to replace an unmanaged CA bundle')
        for p in (bundle,trustdir/'use-ca.sh'):
            if p.exists(): (logdir/('before-'+p.name)).write_bytes(p.read_bytes())
        if not marker.exists(): atomic_write(marker,'CSE trust maintenance v2\n')
        empty.mkdir(mode=0o2775,exist_ok=True)
        if empty.stat().st_uid == os.geteuid():
            os.chown(str(empty), -1, cse_gid); os.chmod(str(empty), 0o2775)
        if any(empty.iterdir()): raise RuntimeError('Expected dedicated empty CA directory')
        atomic_write(bundle,bundle_text)
        atomic_write(trustdir/'use-ca.sh','# Source after loading your CSE module.\n'+''.join('export %s=%s\n'%(k,shlex.quote(v)) for k,v in values.items()))
        env.update(values)
        env['CONDA_OFFLINE'] = 'true' if args.offline else 'false'
    for i,prefix in enumerate(prefixes):
        row = {'prefix':str(prefix),'status':'incomplete','issues':[]};results.append(row)
        say('\nPrefix: '+str(prefix))
        if not (prefix/'conda-meta/history').is_file() or not maintainable(prefix) or not maintainable(prefix/'conda-meta'):
            row['status']='skipped';row['issues'].append('Not an accessible user/group-maintainable prefix')
            say('SKIP: '+row['issues'][0]);continue
        try:
            meta = records(prefix)
            targets,allowed,specs = plan_specs(meta,args.upgrade_conda)
            say('Package targets: '+(', '.join(sorted(targets)) or 'none'))
            audit = {'packages':{},'bundles':{}}
            py = prefix/'bin/python'
            if 'python' in meta:
                audit = runjson([py,'-I','-c',AUDIT])
                (logdir/('%03d-before-audit.json'%i)).write_text(json.dumps(audit,indent=2))
                unmanaged={n for n in MINIMUM if n in audit['packages'] and n not in meta and version(audit['packages'][n]) < version(MINIMUM[n])}
                if unmanaged:
                    row['issues'].append('Outdated non-conda tools require reviewed conda-forge migration: '+', '.join(sorted(unmanaged)))
                if 'pip' in audit['packages'] and audit['python'] < [3,10] and version(audit['packages']['pip']) < version(MINIMUM['pip']):
                    row['issues'].append('Old pip on Python <3.10 needs a reviewed compatible remediation')
            if args.apply:
                for relative in ('.condarc','conda-meta/state','conda-meta/history'):
                    p=prefix/relative
                    if p.is_file(): (logdir/('%03d-before-'%i+relative.replace('/','_'))).write_bytes(p.read_bytes())
                (logdir/('%03d-before-explicit.txt'%i)).write_text(run([conda,'list','-p',prefix,'--explicit']).stdout)
                if row['issues']: raise RuntimeError('Unsupported old pip; prefix left unchanged')
                if targets:
                    cmd=[conda,'install','-p',prefix,'--solver','classic','--freeze-installed','--json']+CHANNEL_ARGS+specs
                    if args.offline: cmd.append('--offline')
                    plan=runjson(cmd+['--dry-run'])
                    (logdir/('%03d-plan.json'%i)).write_text(json.dumps(plan,indent=2))
                    changed=check_plan(plan,allowed);say('Validated management changes: '+(', '.join(changed) or 'none'))
                    # Lock the planned final versions/builds before the execution solve.
                    final={n:(r['version'],r['build']) for n,r in meta.items()}
                    for r in plan.get('actions',{}).get('LINK',[]):
                        final[r['name']]=(r['version'],r.get('build_string') or r.get('build'))
                    if any(not b for v,b in final.values()):raise RuntimeError('Plan omitted build identifiers')
                    exact=[n+'='+v+'='+b for n,(v,b) in sorted(final.items())]
                    execution=[conda,'install','-p',prefix,'--solver','classic','--freeze-installed','--json','--yes']+CHANNEL_ARGS+exact
                    if args.offline: execution.append('--offline')
                    runjson(execution)
                run([conda,'config','--file',prefix/'.condarc','--set','ssl_verify',bundle])
                run([conda,'env','config','vars','set','-p',prefix]+[k+'='+v for k,v in values.items()])
                after_meta=records(prefix)
                if args.upgrade_conda and 'conda' in meta and version(after_meta['conda']['version']) < (26,9,4):
                    raise RuntimeError('Conda still below the requested minimum')
                for n in set(MINIMUM)&set(meta):
                    if version(after_meta[n]['version'])<version(MINIMUM[n]):raise RuntimeError('Package still below minimum: '+n)
                if 'python' in meta:
                    after=runjson([py,'-I','-c',AUDIT])
                    for n in ('pip','certifi','uv','sigstore'):
                        if n in after['packages'] and version(after['packages'][n])<version(MINIMUM[n]):raise RuntimeError('Runtime package below minimum: '+n)
                    # Check actual embedded bundles in addition to selected CSE bundle.
                    for label,path in after['bundles'].items():
                        if path and Path(path).is_file():
                            present={h for h,pem in pem_entries(Path(path).read_text())}&set(ROOTS)
                            if present:row['issues'].append('Known incident roots remain in '+label+': '+path)
                if 'sigstore' in after_meta and 'python' in meta:
                    failure = sigstore_startup(py,env,log)
                    if failure: row['issues'].append(failure)
                for rel in ('ssl/cacert.pem','ssl/cert.pem'):
                    candidate=prefix/rel
                    if candidate.is_file() and {h for h,pem in pem_entries(candidate.read_text())}&set(ROOTS):
                        row['issues'].append('Known incident roots remain in '+str(candidate))
                if args.chains_dir:
                    verify_chains(prefix/'bin/openssl' if (prefix/'bin/openssl').is_file() else Path('/usr/bin/openssl'),bundle,args.chains_dir.resolve(),env,run)
            else:
                for n,minimum in MINIMUM.items():
                    if n in meta:say('%s: %s; requested minimum %s'%(n,meta[n]['version'],minimum))
                say('Would configure conda/activation to use: '+str(bundle))
            for n in ('pixi',):
                if n in meta or n in audit['packages']:row['issues'].append(n+' needs separate embedded-tool/dependency review')
            row['issues']+=public_permissions(prefix,base,args.apply,say)
            row['status']='incomplete' if row['issues'] else ('updated' if args.apply else 'previewed')
        except Exception as exc:
            row['issues'].append(str(exc));log.write(traceback.format_exc())
        for issue in row['issues']:say('ATTENTION: '+issue)
        say('Status: '+row['status'])
    (logdir/'summary.json').write_text(json.dumps(results,indent=2))
    say('\nSummary: '+', '.join('%s=%d'%(s,sum(r['status']==s for r in results)) for s in ('previewed','updated','skipped','incomplete')))
    if args.apply:say('For the current shell after loading your module: . '+shlex.quote(str(trustdir/'use-ca.sh')))
    say('No external test endpoints were contacted. OS/proxy trust unchanged.')
    log.close()
    if lockfile:lockfile.close()
    return 2 if any(r['status'] in ('skipped','incomplete') for r in results) else 0


if __name__=='__main__':
    try:sys.exit(main())
    except (Exception,KeyboardInterrupt) as exc:
        print('STOPPED: '+str(exc),file=sys.stderr);sys.exit(2)
