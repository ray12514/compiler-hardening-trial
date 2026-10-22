#!/usr/bin/env python3
"""CSE Miniforge certificate maintenance, revision 7 (2026-10-22).

Python 3.8+, standard library. Run as a maintenance account, not root.
  python3 patch_miniforge_trust.py                       # preview loaded install
  python3 patch_miniforge_trust.py /path/to/miniforge     # explicit install
  python3 patch_miniforge_trust.py --apply               # apply, normal channels
  python3 patch_miniforge_trust.py --apply --offline     # approved cached packages
  python3 patch_miniforge_trust.py --apply --upgrade-conda
  python3 patch_miniforge_trust.py --report latest        # explain saved logs only

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
Inaccessible/missing discovery paths and ineligible environments are skipped and
reported. Permission traversal catches errors per path and continues with siblings.
Hidden directories are not skipped merely for being hidden. --exclude also prunes
nested paths from permission traversal. Access/ownership/ACL skips alone are
nonfatal warnings (exit 0); real package/check failures remain incomplete (exit 2).
summary.json distinguishes updated-with-skips from fully updated; skipped-paths.txt
and skipped-paths.json list full paths, owners, groups, stages and reasons.
Default output is concise; --verbose shows path details. Full details are logged.
Final summaries always repeat package requests, permission counts and failure reasons.
Per-owner skip reports are private review aids. A skip is not protection.
--report LOG_DIR (or latest) reads prior summaries/logs without updates or network.
New command failures save separate JSON records with arguments, exit status, phase
and stdout/stderr; final summaries include the underlying error rather than a wrapper.

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
import pwd
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


def public_permissions(prefix, base, apply, say, skipped=None, excludes=(), stats=None):
    problems, changed = [], 0
    if stats is None: stats = {}
    stats.update(planned=0, changed=0, group_changes=0, mode_changes=0, parent_warnings=0)
    shared_gid = maintenance_gid()
    exclusions = [Path(os.path.abspath(os.path.expanduser(str(p)))) for p in excludes]
    def excluded(p):
        return any(p == x or x in p.parents for x in exclusions)
    def note(p, reason, stage='permissions'):
        message = str(p) + ': ' + str(reason)
        problems.append(message)
        if skipped is not None:
            skipped.append({'path':str(p),'stage':stage,'reason':str(reason),
                            'prefix':str(prefix)})
        say('SKIP PATH: ' + message)
    def visit(p):
        nonlocal changed
        st = p.lstat()
        if stat.S_ISLNK(st.st_mode): return
        if not (stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode)): return
        if stat.S_ISDIR(st.st_mode) and not os.access(str(p),os.R_OK|os.X_OK):
            note(p,'Directory is not readable/traversable; left unchanged');return
        if hasattr(os,'listxattr') and 'system.posix_acl_access' in os.listxattr(str(p)):
            note(p,'Extended ACL needs owner/admin review');return
        old=stat.S_IMODE(st.st_mode)
        if stat.S_ISREG(st.st_mode) and old & (stat.S_ISUID|stat.S_ISGID):
            note(p,'Privileged file needs owner/admin review');return
        new=public_mode(old,stat.S_ISDIR(st.st_mode))
        if old == new and shared_gid == st.st_gid:return
        if st.st_uid != os.geteuid():
            note(p,'Owner must set group cse and required permissions');return
        stats['planned'] += 1
        stats['group_changes'] += int(shared_gid != st.st_gid)
        stats['mode_changes'] += int(old != new)
        say('PERMISSION: %s | group %s -> cse | mode %04o -> %04o' % (p,st.st_gid,old,new))
        if not apply:return
        if stat.S_ISREG(st.st_mode) and st.st_nlink > 1:
            fd,tmp=tempfile.mkstemp(prefix='.trust-mode-',dir=str(p.parent));os.close(fd)
            try:
                shutil.copy2(str(p),tmp);os.chown(tmp,-1,shared_gid);os.chmod(tmp,new)
                os.replace(tmp,str(p))
            finally:
                if os.path.exists(tmp):os.unlink(tmp)
        else:
            if shared_gid != st.st_gid:os.chown(str(p),-1,shared_gid)
            os.chmod(str(p),new)
        changed += 1
        stats['changed'] = changed
    def safe_visit(p):
        try:visit(p)
        except OSError as exc:note(p,exc)
    def walk_error(exc):note(exc.filename or prefix,exc)
    for root,dirs,files in os.walk(str(prefix),followlinks=False,onerror=walk_error):
        root=Path(root)
        if excluded(root):dirs[:]=[];continue
        if not os.access(str(root),os.R_OK|os.X_OK):
            note(root,'Directory is not readable/traversable; left unchanged');dirs[:]=[];continue
        safe_visit(root)
        keep=[]
        for name in dirs:
            p=root/name
            try:
                if excluded(p):
                    say('EXCLUDED: '+str(p));continue
                if secret(p):
                    say('Preserving private-path permissions: '+str(p));continue
                if p.is_symlink():continue
                if not os.access(str(p),os.R_OK|os.X_OK):
                    note(p,'Directory is not readable/traversable; left unchanged');continue
                if prefix == base and name in ('pkgs','envs') and root == base:
                    safe_visit(p);continue
                if (p/'conda-meta/history').is_file():continue
                keep.append(name)
            except OSError as exc:note(p,exc)
        dirs[:]=keep
        for name in files:
            p=root/name
            if excluded(p):continue
            if secret(p):
                say('Preserving private-path permissions: '+str(p));continue
            safe_visit(p)
    for p in prefix.parents:
        try:
            if not p.stat().st_mode & stat.S_IXOTH:
                stats['parent_warnings'] += 1
                note(p,'Parent lacks other-traverse bit; group/ACL access may still allow some users. Owner/admin must review outside-group access; parent left unchanged','parent-access')
        except OSError as exc:note(p,exc)
    say('Permissions %s: %d paths' % ('changed' if apply else 'would change',changed if apply else stats['planned']))
    return problems



AUDIT = r'''
import sys, json, ssl, importlib.util
from importlib import metadata
d = {'python': list(sys.version_info[:3]), 'packages': {}, 'bundles': {}, 'provenance': {}}
for name in ('pip','certifi','uv','sigstore','pixi'):
    try:
        dist = metadata.distribution(name)
        d['packages'][name] = dist.version
        d['provenance'][name] = {'installer':(dist.read_text('INSTALLER') or '').strip(),
                                  'location':str(dist.locate_file(''))}
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


def discover(base, conda, env, includes, scans, excludes, skipped=None):
    def note(p,reason):
        if skipped is not None:skipped.append({'path':str(p),'stage':'discovery','reason':str(reason)})
    def canonical(p):
        p=Path(p).expanduser()
        try:return p.resolve()
        except OSError as exc:
            note(p,exc);return Path(os.path.abspath(str(p)))
    exclusions=[canonical(p) for p in excludes]
    def excluded(p):return any(p == x or x in p.parents for x in exclusions)
    paths={base}
    try:
        inventory=json.loads(capture([conda,'env','list','--json'],env))
        candidates=inventory['envs']
    except (RuntimeError,ValueError,KeyError,OSError) as exc:
        note(conda,'conda env list failed; trying the local registry: '+str(exc))
        candidates=[]
        registry=Path.home()/'.conda/environments.txt'
        try:
            if registry.is_file():candidates=registry.read_text().splitlines()
        except OSError as registry_error:note(registry,registry_error)
    for p in list(candidates)+list(includes):
        if str(p).strip():paths.add(canonical(p))
    envdir=base/'envs'
    try:
        if envdir.is_dir():
            for p in envdir.iterdir():
                if excluded(p):continue
                try:
                    if not os.access(str(p),os.R_OK|os.X_OK):
                        note(p,'Cannot inspect possible environment; directory inaccessible');continue
                    if (p/'conda-meta/history').is_file():paths.add(canonical(p))
                except OSError as exc:note(p,exc)
    except OSError as exc:note(envdir,exc)
    for scan in scans:
        scan=canonical(scan)
        if excluded(scan):continue
        if not os.access(str(scan),os.R_OK|os.X_OK):
            note(scan,'Scan root missing or inaccessible');continue
        def walk_error(exc):note(exc.filename or scan,exc)
        for root,dirs,files in os.walk(str(scan),followlinks=False,onerror=walk_error):
            root=Path(root)
            if excluded(root):dirs[:]=[];continue
            try:
                if (root/'conda-meta/history').is_file():paths.add(canonical(root))
            except OSError as exc:note(root,exc)
            keep=[]
            for name in dirs:
                p=root/name
                if name in ('pkgs','conda-meta','.git') or excluded(p):continue
                try:
                    if p.is_symlink():continue
                    if not os.access(str(p),os.R_OK|os.X_OK):
                        note(p,'Directory is not readable/traversable; scan skipped');continue
                    keep.append(name)
                except OSError as exc:note(p,exc)
            dirs[:]=keep
    return sorted([p for p in paths if not excluded(p)],key=lambda p:(p != base,str(p)))


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


def path_owner(path):
    """Report the actual path owner only; never infer ownership from a parent."""
    result = {'owner':'unknown','uid':None,'group':'unknown','gid':None}
    try:
        st = Path(path).lstat()
    except OSError:
        return result
    result.update(uid=st.st_uid,gid=st.st_gid)
    try: result['owner'] = pwd.getpwuid(st.st_uid).pw_name
    except (KeyError,OSError): result['owner'] = 'uid:%d' % st.st_uid
    try: result['group'] = grp.getgrgid(st.st_gid).gr_name
    except (KeyError,OSError): result['group'] = 'gid:%d' % st.st_gid
    return result


def write_skip_reports(logdir, skipped_paths):
    # One path can affect multiple prefixes; keep that association without duplicates.
    merged = {}
    for item in skipped_paths:
        key = (item['path'],item['stage'],item['reason'])
        if key not in merged:
            merged[key] = dict(item,**path_owner(item['path']))
            merged[key]['prefixes'] = []
        if item.get('prefix') and item['prefix'] not in merged[key]['prefixes']:
            merged[key]['prefixes'].append(item['prefix'])
    rows = list(merged.values())
    def line(r):
        return '%s | owner=%s uid=%s group=%s | %s | environments=%s | %s\n' % (
            r['stage'],r['owner'],r['uid'],r['group'],r['path'],
            ', '.join(r['prefixes']) or 'not established',r['reason'])
    (logdir/'skipped-paths.json').write_text(json.dumps(rows,indent=2))
    (logdir/'skipped-paths.txt').write_text(''.join(map(line,rows)))
    by_owner = {}
    for row in rows: by_owner.setdefault(row['owner'],[]).append(row)
    (logdir/'skipped-by-owner.json').write_text(json.dumps(by_owner,indent=2))
    for owner,items in by_owner.items():
        # UID-based filename avoids trusting account names as paths.
        uid = items[0]['uid']
        name = 'skipped-owner-%s.txt' % (uid if uid is not None else 'unknown')
        (logdir/name).write_text('Review these paths; this report does not assert they were updated.\n'+''.join(map(line,items)))
    return rows


def final_summary(results, apply, bundle, say):
    say('\nFinal summary (%s):' % ('APPLY' if apply else 'LOCAL PREVIEW; nothing applied'))
    for row in results:
        owner = row.get('ownership',{})
        say('%s | %s | owner=%s group=%s' % (row['prefix'],row['status'],owner.get('owner','unknown'),owner.get('group','unknown')))
        for target in row.get('package_targets',[]):
            say('  Package target: %s %s -> %s' % (target['name'],target['current'],target['request']))
        for change in row.get('package_plan',[]):
            say('  Solver plan: %s %s -> %s (build %s)' % (change['name'],change['before'],change['after'],change['build']))
        for change in row.get('package_changes',[]):
            say('  Verified package: %s %s -> %s' % (change['name'],change['before'],change['after']))
        stats = row.get('permissions',{})
        if stats:
            say('  Permissions: %d paths %s; %d group changes planned to cse; %d mode changes planned; %d parent access warnings' % (
                stats.get('changed' if apply else 'planned',0),'changed' if apply else 'would change',
                stats.get('group_changes',0),stats.get('mode_changes',0),stats.get('parent_warnings',0)))
        if row.get('trust_configuration'):
            say('  Trust configuration: '+row['trust_configuration']+' '+str(bundle))
        if row.get('permission_warnings'): say('  Permission/access skips: %d; see skip reports' % len(row['permission_warnings']))
        if row.get('phase') and row['status']=='incomplete': say('  Failed/review phase: '+row['phase'])
        for issue in row['issues']: say('  Reason: '+issue)
    say('Environment counts: '+', '.join('%s=%d'%(s,sum(r['status']==s for r in results)) for s in ('previewed','previewed-with-skips','updated','updated-with-skips','skipped','incomplete')))
    say('Counts are environments, not package versions. Incomplete means a required package/check failed or needs review; reasons appear above.')
    if not apply: say('Preview targets are requests, not solved upgrades. No dependency solve ran; exact versions/builds are validated during apply.')


def diagnostic_text(stdout, stderr):
    """Extract conda's actual JSON error or meaningful exception, not our wrapper."""
    decoder = json.JSONDecoder()
    for stream in (stdout,stderr):
        for match in re.finditer(r'(?m)^\s*\{',stream):
            try: obj,_ = decoder.raw_decode(stream[match.start():].lstrip())
            except ValueError: continue
            if isinstance(obj,dict):
                parts = [str(obj[k]) for k in ('exception_name','error','message') if obj.get(k)]
                if parts: return '\n'.join(dict.fromkeys(parts))[:2400]
    combined = stderr+'\n'+stdout
    lines = [line.strip() for line in combined.splitlines() if line.strip()]
    useful = [line for line in lines if re.search(
        r'PermissionError|Permission denied|Errno \d+|[A-Za-z]+Error:|[A-Za-z]+Error\b|'
        r'CERTIFICATE_VERIFY_FAILED|Unsatisfiable|not writable|not found|No space left|Read-only file system|'
        r'cannot execute|GLIBC_|failed to|Could not|HTTP [45]\d\d',line,re.I)
        and not line.startswith(('except ','if ','raise ','File '))
        and not any(x in line for x in ('Command failed; see private','raise RuntimeError(', 'raise command_failure', 'if r.returncode'))]
    if useful: return '\n'.join(useful[-8:])[:2400]
    return '\n'.join(lines[-8:])[:2400] or 'Command returned no diagnostic output'


def failure_category(text):
    value = text.lower()
    if 'non-conda' in value or 'conda-forge migration' in value:
        return 'Mixed package ownership', 'Review the named pip/uv-managed tool and its requirements; do not overwrite it with conda in bulk.'
    if any(x in value for x in ('permission denied','permissionerror','not writable','notwritableerror','read-only file system')):
        return 'Filesystem access', 'Check the exact denied path, its parent traversal, ACLs, mount policy and cache location; environment ownership alone is insufficient.'
    if any(x in value for x in ('certificate_verify_failed','sslerror','ssl verification','certificate verify failed','proxyerror')):
        return 'TLS/proxy access', 'Review CA/proxy configuration and the specific endpoint; do not disable TLS verification.'
    if any(x in value for x in ('packagesnotfound','unsatisfiable','conflict','could not solve')):
        return 'Package availability/dependencies', 'Check approved conda-forge mirror availability and installed pins/Python compatibility.'
    if any(x in value for x in ('connectionerror','condahttperror','timed out','name resolution','network is unreachable')):
        return 'Repository/network access', 'Check the approved mirror/proxy route or offline cache availability.'
    if any(x in value for x in ('jsondecodeerror','invalid json','not valid json','no json')):
        return 'Invalid command output', 'Inspect the recorded stdout/stderr for startup errors or output preceding JSON.'
    return 'Other/unresolved', 'Use the command and diagnostic below; the old generic wrapper alone does not identify the cause.'


def legacy_failure_details(logtext, prefix):
    """Best-effort extraction from older logs; never execute logged commands."""
    chunks = re.split(r'(?m)^Prefix: ',logtext)
    section = next((chunk.split('\nFinal summary',1)[0] for chunk in chunks[1:]
                    if chunk.splitlines() and chunk.splitlines()[0].strip()==prefix), '')
    commands = list(re.finditer(r'(?m)^\$ ([^\n]*)\n',section))
    if not commands: return None
    # Older wrappers raise after the failed command, so the last command before
    # the wrapper is the candidate. This is inferred, not a recorded return code.
    wrapper = section.find('RuntimeError: Command failed; see private run.log')
    if wrapper < 0: return None
    candidates = [m for m in commands if m.start()<wrapper]
    if not candidates: return None
    match = candidates[-1]
    output = section[match.end():wrapper]
    detail = diagnostic_text(output,'')
    return {'command':match.group(1)[:500], 'detail':detail,'returncode':None,
            'phase':'legacy log (inferred command; return code not recorded)'}


def report_existing(directory, verbose=False):
    if str(directory)=='latest':
        root = Path.home()/'.cse-trust-logs'
        candidates = [p for p in root.iterdir() if p.is_dir() and (p/'summary.json').is_file()]
        if not candidates: raise RuntimeError('No completed summary found under '+str(root))
        directory = max(candidates,key=lambda p:p.name)
    directory = Path(directory).expanduser().resolve(strict=True)
    results = json.loads((directory/'summary.json').read_text())
    logtext = (directory/'run.log').read_text(errors='replace') if (directory/'run.log').is_file() else ''
    print('READ-ONLY REPORT: '+str(directory))
    mode = next((line for line in logtext.splitlines() if line.startswith('Mode: ')),'Mode: not recorded')
    print('Saved run '+mode)
    print('No environments, packages, permissions or certificates are changed. No network commands run.')
    counts = {}
    failures = []
    for row in results:
        counts[row['status']] = counts.get(row['status'],0)+1
        if row['status'] not in ('incomplete','skipped') and not verbose: continue
        issues = row.get('issues',[])
        evidence = row.get('command_failures',[])
        if not evidence and any('Command failed; see private run.log' in issue for issue in issues):
            inferred = legacy_failure_details(logtext,row['prefix'])
            if inferred: evidence = [inferred]
        cause_text = '\n'.join(issues+[e['detail'] for e in evidence])
        category,advice = failure_category(cause_text)
        failures.append(category)
        print('\n%s | %s | owner=%s' % (row['prefix'],row['status'],row.get('ownership',{}).get('owner','unknown')))
        print('  Category: '+category)
        print('  Changes started: '+str(row.get('changes_started','not recorded'))+' (not a transaction/rollback guarantee)')
        for issue in issues:
            if 'Command failed; see private run.log' not in issue: print('  Reason: '+issue)
        for event in evidence:
            print('  Phase: '+event.get('phase','not recorded'))
            print('  Command: '+event['command'])
            print('  Return code: '+str(event.get('returncode','not recorded')))
            print('  Diagnostic: '+event['detail'].replace('\n','\n    '))
            if event.get('file'): print('  Full command output: '+str(directory/event['file']))
        if not evidence and any('Command failed; see private run.log' in issue for issue in issues):
            print('  Diagnostic unavailable in this summary; legacy run.log extraction found no matching command.')
        print('  Next step: '+advice)
        if row.get('non_conda_tools'):
            print('  Non-conda inventory: '+json.dumps(row['non_conda_tools'],sort_keys=True))
    print('\nEnvironment counts: '+', '.join('%s=%d'%item for item in sorted(counts.items())))
    print('Failure/review categories: '+(', '.join('%s=%d'%(c,failures.count(c)) for c in sorted(set(failures))) or 'none'))
    print('updated-with-skips means work completed with access/permission exceptions; it is not a failed package update.')
    print('Legacy diagnostics are best-effort evidence from saved logs, not a new system test.')
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('miniforge', nargs='?', type=Path)
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--report',type=Path,metavar='LOG_DIR_OR_latest',help='Read an existing summary/run.log and explain failures; no updates, group checks or network')
    ap.add_argument('--verbose',action='store_true',help='Show per-path permission details and subprocess commands; full details are always logged')
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
    if args.report:
        if args.apply: ap.error('--report cannot be combined with --apply')
        return report_existing(args.report,args.verbose)
    if os.geteuid() == 0: ap.error('Run as the software maintenance account, not root')
    cse_gid = maintenance_gid()  # validate before any deployment changes
    os.umask(0o002)
    env = safe_environment()
    base = find_base(args.miniforge,env); conda = base/'bin/conda'
    if not maintainable(base): raise RuntimeError('No user/group maintenance access to base')
    config = json.loads(capture([conda,'config','--show','ssl_verify','--json'],env))
    source = choose_source(args,config,base)
    bundle_text, removed = filtered_bundle([source] + args.extra_ca)
    skipped_paths = []
    prefixes = discover(base,conda,env,args.include,args.scan_root,args.exclude,skipped_paths)
    logdir = (args.log_dir or Path.home()/'.cse-trust-logs'/datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')).expanduser().resolve()
    if any(logdir == p or p in logdir.parents for p in prefixes):
        raise RuntimeError('Logs must be outside all selected environment trees')
    logdir.mkdir(mode=0o700,parents=True,exist_ok=False)
    os.chmod(str(logdir),0o700)
    log = open(str(logdir/'run.log'),'w',buffering=1)
    def say(s): print(s,flush=True);log.write(s+'\n')
    def detail(s):
        if args.verbose: print(s,flush=True)
        log.write(s+'\n')
    say('Mode: '+('APPLY' if args.apply else 'LOCAL PREVIEW; no network operations'))
    say('Package source: conda-forge ONLY; external plugins disabled; no PyPI fallback')
    say('Base: '+str(base)); say('Source CA: '+str(source));say('Private logs: '+str(logdir))
    say('Current UID/groups: %s / %s' % (os.geteuid(),','.join(map(str,sorted(groups())))))
    say('Shared permissions target: cse (GID %d); directories 2775, files 0664, executables 0775' % cse_gid)
    say('Roots removed from CSE copy: '+(', '.join(removed) or 'none of the four matched'))
    say('This is local mitigation, not evidence of proxy remediation or a full trust-store refresh.')
    command_number = 0
    def record_failure(cmd, stdout, stderr, code, reason=None):
        nonlocal command_number
        command_number += 1
        filename = 'failed-command-%03d.json' % command_number
        display = shlex.join(list(map(str,cmd))) if '-c' not in cmd else str(cmd[0])+' -I -c <local Python audit>'
        diagnostic = reason or diagnostic_text(stdout,stderr)
        event = {'command':display[:500],'detail':diagnostic,'returncode':code,'file':filename,
                 'phase':row.get('phase','not recorded')}
        (logdir/filename).write_text(json.dumps(dict(event,argv=list(map(str,cmd)),stdout=stdout,stderr=stderr),indent=2))
        row.setdefault('command_failures',[]).append(event)
        return RuntimeError('Command failed during %s (exit %s): %s | %s | full output: %s' %
                            (event['phase'],code,display[:180],diagnostic,logdir/filename))
    def run(cmd, allow_failure=False):
        detail('$ '+shlex.join(map(str,cmd)))
        try:
            r = subprocess.run(list(map(str,cmd)),env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        except OSError as exc:
            raise record_failure(cmd,'',str(exc),None) from exc
        log.write(r.stdout+r.stderr+'\n')
        if r.returncode and not allow_failure:
            raise record_failure(cmd,r.stdout,r.stderr,r.returncode)
        return r
    def runjson(cmd):
        r = run(cmd)
        try: data = json.loads(r.stdout)
        except ValueError as exc:
            raise record_failure(cmd,r.stdout,r.stderr,r.returncode,'Invalid JSON output: '+diagnostic_text(r.stdout,r.stderr)) from exc
        if isinstance(data,dict) and data.get('success') is False:
            raise record_failure(cmd,r.stdout,r.stderr,r.returncode)
        return data
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
        row = {'prefix':str(prefix),'status':'incomplete','issues':[],'skipped_paths':[],'changes_started':False,'ownership':path_owner(prefix)};results.append(row)
        say('\nPrefix: '+str(prefix))
        try:
            eligible = (prefix/'conda-meta/history').is_file() and maintainable(prefix) and maintainable(prefix/'conda-meta')
            eligible = eligible and os.access(str(prefix),os.R_OK|os.X_OK) and os.access(str(prefix/'conda-meta'),os.R_OK|os.X_OK)
            reason = 'Not an accessible user/group-maintainable prefix'
        except OSError as exc:
            eligible = False;reason = str(exc)
        if not eligible:
            row['status']='skipped';row['issues'].append(reason)
            skipped_paths.append({'path':str(prefix),'stage':'environment','reason':reason,'prefix':str(prefix)})
            say('SKIP ENVIRONMENT: '+str(prefix)+': '+reason);continue
        try:
            row['phase'] = 'read conda package metadata'
            meta = records(prefix)
            targets,allowed,specs = plan_specs(meta,args.upgrade_conda)
            row['package_targets'] = [{'name':n,'current':meta[n]['version'],'request':('>='+MINIMUM[n] if n in MINIMUM else ('>=26.9.4' if n == 'conda' else 'compatible conda-forge build'))} for n in sorted(targets)]
            detail('Package targets: '+(', '.join(sorted(targets)) or 'none'))
            audit = {'packages':{},'bundles':{}}
            py = prefix/'bin/python'
            if 'python' in meta:
                row['phase'] = 'local Python package audit'
                audit = runjson([py,'-I','-c',AUDIT])
                (logdir/('%03d-before-audit.json'%i)).write_text(json.dumps(audit,indent=2))
                unmanaged={n for n in MINIMUM if n in audit['packages'] and n not in meta and version(audit['packages'][n]) < version(MINIMUM[n])}
                if unmanaged:
                    row['non_conda_tools'] = [{'name':n,'current':audit['packages'][n],'minimum':MINIMUM[n],**audit.get('provenance',{}).get(n,{})} for n in sorted(unmanaged)]
                    row['issues'].append('Outdated non-conda tools require reviewed conda-forge migration: '+', '.join(sorted(unmanaged)))
                if 'pip' in audit['packages'] and audit['python'] < [3,10] and version(audit['packages']['pip']) < version(MINIMUM['pip']):
                    row['issues'].append('Old pip on Python <3.10 needs a reviewed compatible remediation')
            if args.apply:
                if row['issues']: raise RuntimeError('Package review required; no package/configuration/permission changes attempted for this prefix')
                row['phase'] = 'save configuration and conda package inventory'
                for relative in ('.condarc','conda-meta/state','conda-meta/history'):
                    p=prefix/relative
                    if p.is_file(): (logdir/('%03d-before-'%i+relative.replace('/','_'))).write_bytes(p.read_bytes())
                (logdir/('%03d-before-explicit.txt'%i)).write_text(run([conda,'list','-p',prefix,'--explicit']).stdout)
                if targets:
                    row['phase'] = 'solve package update (dry run)'
                    cmd=[conda,'install','-p',prefix,'--solver','classic','--freeze-installed','--json']+CHANNEL_ARGS+specs
                    if args.offline: cmd.append('--offline')
                    plan=runjson(cmd+['--dry-run'])
                    (logdir/('%03d-plan.json'%i)).write_text(json.dumps(plan,indent=2))
                    changed=check_plan(plan,allowed)
                    row['package_plan'] = [{'name':r['name'],'before':meta.get(r['name'],{}).get('version','absent'),'after':r['version'],'build':r.get('build_string') or r.get('build')} for r in plan.get('actions',{}).get('LINK',[])]
                    detail('Validated management changes: '+(', '.join(changed) or 'none'))
                    # Lock the planned final versions/builds before the execution solve.
                    final={n:(r['version'],r['build']) for n,r in meta.items()}
                    for r in plan.get('actions',{}).get('LINK',[]):
                        final[r['name']]=(r['version'],r.get('build_string') or r.get('build'))
                    if any(not b for v,b in final.values()):raise RuntimeError('Plan omitted build identifiers')
                    exact=[n+'='+v+'='+b for n,(v,b) in sorted(final.items())]
                    execution=[conda,'install','-p',prefix,'--solver','classic','--freeze-installed','--json','--yes']+CHANNEL_ARGS+exact
                    if args.offline: execution.append('--offline')
                    row['phase'] = 'install validated package plan'
                    row['changes_started']=True
                    runjson(execution)
                row['phase'] = 'configure prefix trust'
                row['changes_started']=True
                run([conda,'config','--file',prefix/'.condarc','--set','ssl_verify',bundle])
                run([conda,'env','config','vars','set','-p',prefix]+[k+'='+v for k,v in values.items()])
                row['phase'] = 'verify updated packages and trust bundles'
                after_meta=records(prefix)
                row['package_changes'] = [{'name':n,'before':meta.get(n,{}).get('version','absent'),'after':r['version']} for n,r in sorted(after_meta.items()) if n not in meta or (r['version'],r['build']) != (meta[n]['version'],meta[n]['build'])]
                row['trust_configuration'] = 'configured to use'
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
                    if n in meta:detail('%s: %s; requested minimum %s'%(n,meta[n]['version'],minimum))
                row['trust_configuration'] = 'would configure conda/activation to use'
                detail('Would configure conda/activation to use: '+str(bundle))
            for n in ('pixi',):
                if n in meta or n in audit['packages']:row['issues'].append(n+' needs separate embedded-tool/dependency review')
            row['phase'] = 'normalize shared permissions'
            row['permissions'] = {}
            permissions = public_permissions(prefix,base,args.apply,detail,row['skipped_paths'],args.exclude,row['permissions'])
            skipped_paths.extend(row['skipped_paths'])
            row['permission_warnings'] = permissions
            row['status']='incomplete' if row['issues'] else (('updated' if args.apply else 'previewed') + ('-with-skips' if permissions else ''))
        except (PermissionError,FileNotFoundError) as exc:
            row['status']='incomplete' if row['changes_started'] else 'skipped'
            row['issues'].append(str(exc))
            skipped_paths.append({'path':str(exc.filename or prefix),'stage':'environment','reason':str(exc),'prefix':str(prefix)})
            log.write(traceback.format_exc())
        except Exception as exc:
            row['issues'].append(str(exc));log.write(traceback.format_exc())
        for issue in row['issues']:say('ATTENTION: '+issue)
        say('Status: '+row['status'])
    (logdir/'summary.json').write_text(json.dumps(results,indent=2))
    skipped_paths = write_skip_reports(logdir,skipped_paths)
    final_summary(results,args.apply,bundle,say)
    if skipped_paths:
        say('Skipped paths/access warnings: %d; owner details: %s' % (len(skipped_paths),logdir/'skipped-paths.txt'))
        say('Reports grouped by owner: '+str(logdir/'skipped-by-owner.json')+' and skipped-owner-UID.txt')
        if args.verbose:
            for r in skipped_paths: say('  %s | owner=%s | %s | %s' % (r['stage'],r['owner'],r['path'],r['reason']))
    say('Full summary: '+str(logdir/'summary.json'))
    if any(r['status']=='incomplete' for r in results): say('Explain this run without retrying: python3 patch_miniforge_trust.py --report '+shlex.quote(str(logdir)))
    if args.apply:say('For the current shell after loading your module: . '+shlex.quote(str(trustdir/'use-ca.sh')))
    say('No external test endpoints were contacted. OS/proxy trust unchanged.')
    log.close()
    if lockfile:lockfile.close()
    return 2 if any(r['status'] == 'incomplete' for r in results) else 0


if __name__=='__main__':
    try:sys.exit(main())
    except (Exception,KeyboardInterrupt) as exc:
        print('STOPPED: '+str(exc),file=sys.stderr);sys.exit(2)
