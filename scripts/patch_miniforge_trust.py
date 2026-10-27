#!/usr/bin/env python3
"""CSE Miniforge certificate maintenance, revision 16 (2026-10-27).

Python 3.8+, standard library. Run as a maintenance account, not root.
  python3 patch_miniforge_trust.py                       # preview loaded install
  python3 patch_miniforge_trust.py /path/to/miniforge     # explicit install
  python3 patch_miniforge_trust.py --apply               # apply, approved channels
  python3 patch_miniforge_trust.py --apply --offline     # approved cached packages
  python3 patch_miniforge_trust.py --apply --upgrade-conda
  python3 patch_miniforge_trust.py --report latest        # explain saved logs only
  python3 patch_miniforge_trust.py --diagnose latest      # dry-run failed solve with conflict details and access checks
  python3 patch_miniforge_trust.py --inspect-trust        # inspect actual CA files
  python3 patch_miniforge_trust.py --base-only            # preview base only
  python3 patch_miniforge_trust.py --only /path/to/env    # preview one prefix
  python3 patch_miniforge_trust.py --all-envs             # opt into discovery
  python3 patch_miniforge_trust.py --trust-only --ca-bundle /path/to/site.pem --apply

No test-site connections, connectivity probes, remote execution or OS writes.
Preview is local-only: inventory, CA inspection, ownership and permissions.
Apply reuses non-default channels recorded in each environment's installed conda
packages, preserving per-package sources where identifiable. conda-forge remains a
fallback; --channel adds an explicit community channel/mirror when metadata is absent. Anaconda defaults/repo.anaconda.com sources are excluded.
All solves use --override-channels and strict channel priority.
There is no PyPI/pip-install fallback. External conda plugins are disabled for
maintenance subprocesses so conda-pypi cannot introduce a PyPI source.
--offline forbids network package retrieval; required packages must be cached or
available in the configured conda-forge mirror/cache. No installer replacement is required.
Run once per distinct shared installation on each system; it does not SSH to hosts.

Default scope is only the loaded base. --only selects exact prefixes; --all-envs
opts into discovery using that conda's env list, immediate envs-dir children and
--include paths. Base discovery uses CONDA_EXE, conda on PATH, or an explicit path. Group maintenance
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
installed through conda. Base also requests conda>=26.9.4 where installed;
--upgrade-conda requests that minimum in non-base prefixes. Related mamba/solver packages are requested together
when installed. Apply checks the installed Conda's approved source for its newest
stable release (cached metadata with --offline), keeping the security minimum.
If base conda is older, apply first solves,
installs and verifies a targeted conda/CA-package bootstrap with that same conda
executable. Only then does it solve the full base update. The bootstrap preserves
the installed Miniforge release/prefix; no installer is downloaded or replaced.
The base prefix permits all installed conda packages, including Python, conda,
NumPy, matplotlib and Kerberos dependencies, to update compatibly. Its solve uses
--update-all and security minimum constraints, then executes the validated exact plan.
Non-base prefixes retain Python/application version+build pins and --freeze-installed.
All use the classic solver. Blocked dependency/mirror plans are reported.
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
--trust-only requires an explicit --ca-bundle and does not invoke conda or update
packages. It writes only the managed CSE trust files and a shell snippet on apply;
existing environments/modulefiles are not configured automatically in this mode.
--inspect-trust reads actual bundles, versions and local configuration separately
from past run status. A stored filtered file is not proof that every app uses it.
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
import threading
import time
import traceback
from urllib.parse import urlsplit, urlunsplit

MINIMUM = {'ca-certificates':'2026.10.19', 'certifi':'2026.10.19',
           'pip':'26.2.2', 'uv':'0.13.4', 'sigstore':'4.5.1'}
CONDA_MINIMUM = '26.9.4'
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
    # --apply must not silently inherit a module/user dry_run setting. Planning
    # commands still pass --dry-run explicitly, which overrides this variable.
    env['CONDA_DRY_RUN'] = 'false'
    # Classic's conflict-hint builder unions a set with a tuple after some
    # --update-deps solves. Keep the solver's normal conflict rejection while
    # bypassing that broken explanation path; do not patch installed Conda.
    env['CONDA_UNSATISFIABLE_HINTS'] = 'false'
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


def plan_specs(meta, upgrade_conda, broad=False, conda_minimum=CONDA_MINIMUM):
    if broad:
        # Base is explicitly authorized for a full compatible conda update.
        targets=set(meta)
        specs=[n+'>='+MINIMUM[n] if n in MINIMUM else ('conda>='+conda_minimum if n=='conda' else n) for n in sorted(targets)]
        return targets,None,specs
    targets = set(meta) & (set(MINIMUM) | MANAGERS)
    if upgrade_conda and 'conda' in meta: targets.add('conda')
    specs = [n + '>=' + MINIMUM[n] if n in MINIMUM else
             ('conda>='+CONDA_MINIMUM if n == 'conda' else n) for n in sorted(targets)]
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
    for action in ('LINK','FETCH'):
        for record in actions.get(action,[]):
            for key in ('url','channel','base_url'):
                if record.get(key) and forbidden_channel(record[key]):
                    raise RuntimeError('Rejected plan source from Anaconda defaults: '+str(record[key]))
    linked = {r['name'] for r in actions.get('LINK',[])}
    unlinked = {r['name'] for r in actions.get('UNLINK',[])}
    if allowed is not None and (linked | unlinked) - allowed:
        raise RuntimeError('Rejected unrelated package changes: ' + ', '.join(sorted((linked|unlinked)-allowed)))
    if unlinked - linked:
        raise RuntimeError('Rejected package removal without replacement: ' + ', '.join(sorted(unlinked-linked)))
    return sorted(linked | unlinked)


def exact_plan_specs(meta, plan, origins, extras, config):
    """Bind the validated final package versions/builds and allowed sources."""
    final={n:(r['version'],r['build']) for n,r in meta.items()}
    final_origins=dict(origins)
    for record in plan.get('actions',{}).get('LINK',[]):
        name=record['name']
        final[name]=(record['version'],record.get('build_string') or record.get('build'))
        _,_,_,planned_origins,_,_=environment_channels({name:record},extras,config)
        if name in planned_origins:final_origins[name]=planned_origins[name]
    if any(not build for value,build in final.values()):
        raise RuntimeError('Plan omitted build identifiers')
    exact=qualify_specs([name+'='+value+'='+build for name,(value,build) in sorted(final.items())],final_origins)
    return final,exact


def conda_bootstrap_status(meta):
    current=meta.get('conda',{}).get('version')
    return {'status':'not-installed' if current is None else
            ('would-update' if version(current)<version(CONDA_MINIMUM) else 'would-check-newest'),
            'before':current,'minimum':CONDA_MINIMUM,
            'policy':'newest stable from approved source; checked during apply'}


def bootstrap_dependencies(meta):
    """Relax installer-history versions for the installed management runtime.

    Classic's --update-deps relaxes dependencies only AFTER an initial solve;
    exact installer history can make that first solve impossible. Explicit site
    pins remain enforced by conda itself.
    """
    targets=set(meta)&(MANAGEMENT_DEPS|MANAGERS|{'conda','python','pip'})
    pending=list(targets)
    while pending:
        for dep in meta[pending.pop()].get('depends',[]):
            name=re.split(r'[ <>=!~\[]',dep,1)[0].rsplit('::',1)[-1]
            if name in meta and name not in targets:
                targets.add(name);pending.append(name)
    return targets


def bootstrap_conda(base, meta, channel_args, origins, extras, config, offline,
                    runjson, logdir, row, say):
    """Upgrade the loaded base's manager before asking it to update all packages."""
    status=row['conda_bootstrap']
    if status['status']=='not-installed':return meta
    required={'ca-certificates':MINIMUM['ca-certificates'],
              'certifi':MINIMUM['certifi']}
    common=[base/'bin/conda','install','-p',base,'--solver','classic','--json','--update-deps']+channel_args
    if offline:common.append('--offline')
    def verify(metadata, stage):
        status[stage+'_conda_version']=metadata.get('conda',{}).get('version')
        for name,minimum in dict({'conda':status['target']},**required).items():
            current=metadata.get(name,{}).get('version')
            if current is None or version(current)<version(minimum):
                raise RuntimeError('Conda bootstrap did not meet required minimum in %s: %s=%s; required >=%s. %s'%(
                    stage,name,current if current is not None else 'missing',minimum,
                    'No bootstrap install was attempted; inspect base-conda-bootstrap-plan.json.' if stage=='plan' else
                    'The install command returned, but installed records do not confirm the upgrade; inspect base-conda-bootstrap-install.json.'))
    try:
        row['phase']='find newest stable base conda'
        # Search only the manager's own approved source. Search does not accept
        # the install-only --strict-channel-priority flag.
        source=origins.get('conda') or requested_channels([],{k:v for k,v in config.items() if k!='pinned_packages'})[1][0]
        search=[base/'bin/conda','search','--json','--override-channels','--channel',source,'conda']
        if offline:search.append('--offline')
        available=runjson(search)
        (logdir/'base-conda-bootstrap-search.json').write_text(json.dumps(available,indent=2))
        stable=[r['version'] for r in available.get('conda',[])
                if re.fullmatch(r'\d+(?:\.\d+)*',str(r.get('version','')))]
        if not stable:raise RuntimeError('No stable Conda release available from '+source+(' in offline metadata' if offline else ''))
        latest=max(stable,key=version)
        if version(latest)<version(CONDA_MINIMUM):
            raise RuntimeError('Newest available Conda is %s from %s; required >=%s%s'%(
                latest,source,CONDA_MINIMUM,' (offline metadata may be stale)' if offline else ''))
        status.update(latest_available=latest,source=source,target=max((latest,status['before']),key=version))
        say('Conda bootstrap: installed=%s; newest stable=%s; source=%s'%(status['before'],latest,source))
        if version(status['before'])>=version(latest):
            status.update(status='not-needed',after=status['before'])
            return meta
        status['status']='would-update'
        bootstrap_origins=dict(origins,conda=source)
        # Old mamba/solver packages can pin conda to an older major release.
        # Request their compatible replacements in this transaction too, rather
        # than making the old solver try to retain a conflicting manager stack.
        managers=sorted(set(meta)&MANAGERS)
        status['manager_targets']=managers
        dependencies=bootstrap_dependencies(meta)-set(required)-{'conda'}
        status['dependency_targets']=sorted(dependencies)
        specs=qualify_specs(['conda=='+status['target']]+[name+'>='+value for name,value in sorted(required.items())]+sorted(dependencies),bootstrap_origins)
        row['phase']='solve base conda bootstrap (dry run)'
        plan=runjson(common+specs+['--dry-run'])
        plan_file=logdir/'base-conda-bootstrap-plan.json'
        plan_file.write_text(json.dumps(plan,indent=2))
        check_plan(plan,None)  # Base dependencies may move; source/removal guards still apply.
        final,exact=exact_plan_specs(meta,plan,bootstrap_origins,extras,config)
        verify({name:{'version':value} for name,(value,build) in final.items()},'plan')
        status['plan_file']=str(plan_file)
        status['package_plan']=[{'name':r['name'],'version':r['version'],
                                'build':r.get('build_string') or r.get('build')}
                               for r in plan.get('actions',{}).get('LINK',[])]
        row['phase']='install validated base conda bootstrap'
        row['changes_started']=True
        execution=runjson(common+['--yes']+exact)
        (logdir/'base-conda-bootstrap-install.json').write_text(json.dumps(execution,indent=2))
        if execution.get('dry_run'):
            raise RuntimeError('Conda returned a dry-run result instead of installing the bootstrap; inspect base-conda-bootstrap-install.json')
        check_plan(execution,None)
        after=records(base)
        verify(after,'installed')
        status.update(status='updated',after=after['conda']['version'])
        say('Conda bootstrap verified: conda=%s; continuing the base update'%status['after'])
        return after
    except Exception as exc:
        status.update(status='incomplete',reason=str(exc))
        raise


def verify_minimums(before, after, upgrade_conda=False, conda_minimum=CONDA_MINIMUM):
    required={n:minimum for n,minimum in MINIMUM.items() if n in before}
    if upgrade_conda and 'conda' in before: required['conda']=conda_minimum
    verified={}
    for name,minimum in sorted(required.items()):
        if name not in after: raise RuntimeError('Required package missing after update: '+name)
        current=after[name]['version']
        if version(current)<version(minimum):
            raise RuntimeError('Package below required minimum: %s=%s; need >=%s'%(name,current,minimum))
        verified[name]={'version':current,'minimum':minimum}
    return verified


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
            if any(word in item['reason'].lower() for word in ('permission denied','not readable','not traversable','owner must')):
                merged[key]['access_details']=access_snapshot(item['path'])
        if item.get('prefix') and item['prefix'] not in merged[key]['prefixes']:
            merged[key]['prefixes'].append(item['prefix'])
    rows = list(merged.values())
    def line(r):
        return '%s | owner=%s uid=%s group=%s | %s | environments=%s | %s\n' % (
            r['stage'],r['owner'],r['uid'],r['group'],r['path'],
            ', '.join(r['prefixes']) or 'not established',r['reason'])+(('  Access: '+json.dumps(r['access_details'],sort_keys=True)+'\n') if r.get('access_details') else '')
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
        if row.get('installed_channels'): say('  Installed channel metadata (historical): '+', '.join(row['installed_channels']))
        if row.get('requested_channels'): say('  Channels used: '+', '.join(row['requested_channels']))
        if row.get('unknown_package_origins'): say('  Missing/invalid origins: %d; details: %s'%(len(row['unknown_package_origins']),row.get('channel_records_file','not recorded')))
        if row.get('excluded_installed_sources'): say('  Excluded installed sources: '+', '.join(sorted({r['source'] for r in row['excluded_installed_sources']})))
        if row.get('package_policy'):say('  Package policy: '+row['package_policy'])
        for target in row.get('package_targets',[]):
            say('  Package target: %s %s -> %s | source=%s' % (target['name'],target['current'],target['request'],target.get('source','not recorded')))
        for change in row.get('package_plan',[]):
            say('  Solver plan: %s %s -> %s (build %s)' % (change['name'],change['before'],change['after'],change['build']))
        for change in row.get('package_changes',[]):
            say('  Verified package: %s %s -> %s' % (change['name'],change['before'],change['after']))
        if row.get('security_verification'):
            say('  Verified required minimums: '+', '.join('%s=%s (>= %s)'%(n,v['version'],v['minimum']) for n,v in sorted(row['security_verification'].items())))
        if row.get('conda_bootstrap'):
            bootstrap=row['conda_bootstrap']
            say('  Conda bootstrap: %s | before=%s | after=%s | minimum=%s'%(
                bootstrap['status'],bootstrap['before'],bootstrap.get('after','not changed/verified'),bootstrap['minimum']))
            if bootstrap.get('latest_available'):
                say('  Newest stable Conda available: %s | source=%s'%(bootstrap['latest_available'],bootstrap['source']))
            elif not apply:
                say('  Conda availability: '+bootstrap.get('policy','checked during apply'))
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
        for snapshot in row.get('access_details',[]): print_access(snapshot,say)
        for event in row.get('command_failures',[]):
            for snapshot in event.get('access_details',[]): print_access(snapshot,say)
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
                parts = [(k+': ' if k in ('path','filename') else '')+str(obj[k]) for k in ('exception_name','error','message','path','filename') if obj.get(k)]
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
    if 'unsupported operand type(s) for |' in value and "'set'" in value and "'tuple'" in value:
        return 'Conda classic conflict-reporting bug', 'Conda crashed while explaining a dependency conflict. Use revision 15 or newer, which disables detailed conflict hints for maintenance subprocesses; inspect any remaining solver failure and explicit pins.'
    if 'non-conda' in value or 'conda-forge migration' in value:
        return 'Mixed package ownership', 'Review the named pip/uv-managed tool and its requirements; do not overwrite it with conda in bulk.'
    if any(x in value for x in ('permission denied','permissionerror','not writable','notwritableerror','read-only file system')):
        return 'Filesystem access', 'Check the exact denied path, its parent traversal, ACLs, mount policy and cache location; environment ownership alone is insufficient.'
    if any(x in value for x in ('certificate_verify_failed','sslerror','ssl verification','certificate verify failed','proxyerror')):
        return 'TLS/proxy access', 'Review CA/proxy configuration and the specific endpoint; do not disable TLS verification.'
    if any(x in value for x in ('unavailableinvalidchannel','channelnotfound','channel is not accessible','invalid requested channel','invalid resolved channel','invalid channel alias/custom')):
        return 'Invalid channel URL/name', 'Use the exact Channels selected/used list and channel-records JSON to identify an empty, malformed or obsolete source. The conda-forge URL includes /conda-forge; do not remove its hosting domain.'
    if any(x in value for x in ('packagesnotfound','unsatisfiable','conflict','could not solve',
                                'no stable conda release','newest available conda')):
        return 'Package availability/dependencies', 'Use --diagnose LOG_DIR for a dry-run conflict explanation and current access checks. The strict-priority note alone does not identify a package or establish that permissions caused this failure.'
    if any(x in value for x in ('connectionerror','condahttperror','timed out','name resolution','network is unreachable')):
        return 'Repository/network access', 'Check the approved mirror/proxy route or offline cache availability.'
    if any(x in value for x in ('jsondecodeerror','invalid json','not valid json','no json')):
        return 'Invalid command output', 'Inspect the recorded stdout/stderr for startup errors or output preceding JSON.'
    return 'Other/unresolved', 'Use the command and diagnostic below; the old generic wrapper alone does not identify the cause.'


def legacy_failure_details(logtext, prefix):
    """Best-effort extraction from older logs; never execute logged commands."""
    chunks = re.split(r'(?m)^Prefix: ',logtext)
    section = next((chunk.split('\nFinal summary',1)[0] for chunk in chunks[1:]
                    if chunk.splitlines() and chunk.splitlines()[0].strip() in (prefix,prefix+' [BASE]')), '')
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


def report_directory(directory):
    if str(directory)=='latest':
        root = Path.home()/'.cse-trust-logs'
        candidates = [p for p in root.iterdir() if p.is_dir() and (p/'summary.json').is_file()]
        if not candidates: raise RuntimeError('No completed summary found under '+str(root))
        directory = max(candidates,key=lambda p:p.name)
    return Path(directory).expanduser().resolve(strict=True)


def report_existing(directory, verbose=False):
    directory = report_directory(directory)
    results = json.loads((directory/'summary.json').read_text())
    logtext = (directory/'run.log').read_text(errors='replace') if (directory/'run.log').is_file() else ''
    print('READ-ONLY REPORT: '+str(directory))
    mode = next((line for line in logtext.splitlines() if line.startswith('Mode: ')),'Mode: not recorded')
    print('Saved run '+mode)
    try:
        cert=json.loads((directory/'certificate-status.json').read_text())
        print('Saved certificate stage: %s | %s | SHA256=%s' % (cert['status'],cert['bundle'],cert.get('sha256')))
    except FileNotFoundError: print('Saved certificate stage: not separately recorded by this script revision; use --inspect-trust to check actual files')
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
        if row.get('conda_bootstrap'):
            bootstrap=row['conda_bootstrap']
            print('  Conda bootstrap: %s | before=%s | after=%s'%(
                bootstrap['status'],bootstrap['before'],bootstrap.get('after','not changed/verified')))
            if bootstrap.get('latest_available'):
                print('  Newest stable Conda available: %s | source=%s'%(bootstrap['latest_available'],bootstrap['source']))
        for issue in issues:
            if 'Command failed; see private run.log' not in issue: print('  Reason: '+issue)
        for event in evidence:
            print('  Phase: '+event.get('phase','not recorded'))
            print('  Command: '+event['command'])
            print('  Return code: '+str(event.get('returncode','not recorded')))
            print('  Diagnostic: '+event['detail'].replace('\n','\n    '))
            snapshots=event.get('access_details') or [access_snapshot(p) for p in denied_paths(event['detail'])]
            for snapshot in snapshots: print_access(snapshot,print)
            if event.get('file'): print('  Full command output: '+str(directory/event['file']))
        if not evidence and any('Command failed; see private run.log' in issue for issue in issues):
            print('  Diagnostic unavailable in this summary; legacy run.log extraction found no matching command.')
        for snapshot in row.get('access_details',[]): print_access(snapshot,print)
        if not evidence:
            for path in denied_paths('\n'.join(issues)): print_access(access_snapshot(path),print)
        print('  Next step: '+advice)
        if row.get('requested_channels'): print('  Channels selected: '+', '.join(row['requested_channels']))
        if row.get('installed_channels'): print('  Installed channel metadata (historical): '+', '.join(row['installed_channels']))
        if row.get('non_conda_tools'):
            print('  Non-conda inventory: '+json.dumps(row['non_conda_tools'],sort_keys=True))
    print('\nEnvironment counts: '+', '.join('%s=%d'%item for item in sorted(counts.items())))
    print('Failure/review categories: '+(', '.join('%s=%d'%(c,failures.count(c)) for c in sorted(set(failures))) or 'none'))
    print('updated-with-skips means work completed with access/permission exceptions; it is not a failed package update.')
    print('Legacy diagnostics are best-effort evidence from saved logs, not a new system test.')
    return 0


CONFLICT_DIAGNOSTIC = r'''
import sys
from conda.resolve import Resolve
from conda.cli.main import main
if not sys.argv[1:] or sys.argv[1] != 'install' or '--dry-run' not in sys.argv or '--yes' in sys.argv:
    raise RuntimeError('Diagnostic process requires an install dry run without --yes')
original = Resolve.build_conflict_map
def compatible(self, specs, specs_to_add=None, history_specs=None):
    return original(self, specs, set(specs_to_add) if specs_to_add is not None else None, history_specs)
Resolve.build_conflict_map = compatible
sys.exit(main(*sys.argv[1:]))
'''


def diagnostic_argv(base, prefix, argv, requested):
    """Rebuild only our install command; saved logs are data, never shell code."""
    if len(argv)<2 or Path(argv[0]).resolve()!=(base/'bin/conda').resolve() or argv[1]!='install':
        raise RuntimeError('Saved failure is not an install from the currently selected base')
    switches={'--json','--offline','--override-channels','--strict-channel-priority',
              '--update-deps','--update-all','--freeze-installed','--dry-run'}
    output=['install'];channels=set(requested);specs=[];prefixes=[];i=2
    while i<len(argv):
        value=argv[i];i+=1
        if value=='--yes':continue
        if value in switches:output.append(value);continue
        if value in ('-p','--solver','--channel'):
            if i==len(argv):raise RuntimeError('Incomplete saved command option: '+value)
            argument=argv[i];i+=1
            if value=='-p':prefixes.append(Path(argument).resolve())
            elif value=='--solver' and argument!='classic':raise RuntimeError('Diagnostic supports the classic solver only')
            elif value=='--channel':
                if invalid_channel_reason(argument) or forbidden_channel(argument):raise RuntimeError('Invalid diagnostic channel')
                channels.add(argument)
            output.extend((value,argument));continue
        if value.startswith('-') or any(c in value for c in '\n\r\x00') or not re.fullmatch(r'(?:.+::)?[\w][\w.-]*(?:[<>=!~].*)?',value):
            raise RuntimeError('Unsupported saved install argument: '+repr(value))
        specs.append(value);output.append(value)
    if prefixes!=[prefix.resolve()] or '--override-channels' not in output or '--strict-channel-priority' not in output:
        raise RuntimeError('Saved command lacks the expected exact prefix and channel policy')
    for spec in specs:
        if '::' in spec:
            origin=spec.rsplit('::',1)[0]
            if origin not in channels or forbidden_channel(origin):raise RuntimeError('Diagnostic package source outside saved channels')
    if not specs:raise RuntimeError('Saved command has no package specifications')
    if '--dry-run' not in output:output.append('--dry-run')
    if '--json' not in output:output.append('--json')
    return output


def diagnose_existing(directory, base, offline=False):
    directory=report_directory(directory)
    rows=json.loads((directory/'summary.json').read_text())
    selected=None
    for row in reversed(rows):
        for event in reversed(row.get('command_failures',[])):
            filename=event.get('file','')
            if not re.fullmatch(r'failed-command-\d+\.json',filename):continue
            path=(directory/filename).resolve()
            if path.parent!=directory:raise RuntimeError('Failure record points outside the log directory')
            record=json.loads(path.read_text());argv=record.get('argv',[])
            if len(argv)>1 and argv[1]=='install':selected=(row,record);break
        if selected:break
    if not selected:raise RuntimeError('No saved install failure to diagnose; use --report for access/configuration failures')
    row,record=selected;prefix=Path(row['prefix']).resolve()
    if any(p==directory or p in directory.parents for p in (base,prefix)):
        raise RuntimeError('Diagnostic logs must be outside the managed prefix trees')
    argv=diagnostic_argv(base,prefix,record['argv'],row.get('requested_channels',[]))
    if offline and '--offline' not in argv:argv.append('--offline')
    print('DIAGNOSTIC DRY RUN: '+str(prefix),flush=True)
    print('Detailed hints enabled with a process-local tuple compatibility fix; installed Conda files are not patched.',flush=True)
    print('No package transaction, CA/configuration update, chmod or chgrp will run. Conda may refresh its repodata cache.',flush=True)
    print('Current UID/groups: %s / %s'%(os.geteuid(),sorted(groups())))
    try:print('cse membership confirmed; GID '+str(maintenance_gid()))
    except RuntimeError as exc:print('cse access note: '+str(exc))
    env=safe_environment()
    try:
        info=json.loads(capture([base/'bin/python','-I','-B','-m','conda','info','--json'],env))
        caches=[Path(p) for p in info.get('pkgs_dirs',[])]
    except (RuntimeError,ValueError) as exc:
        caches=[base/'pkgs'];print('Package-cache discovery failed: '+str(exc))
    for path in dict.fromkeys([base,prefix,prefix/'conda-meta',prefix/'.condarc']+caches):
        print_access(access_snapshot(path),print)
    print('Group write/traverse access can permit package replacement without file ownership; chmod/chgrp of foreign-owned files still needs the owner/admin.',flush=True)
    env.update(CONDA_UNSATISFIABLE_HINTS='true',CONDA_DRY_RUN='true',PYTHONDONTWRITEBYTECODE='1',
               CONDA_OFFLINE='true' if '--offline' in argv else 'false')
    bundle=base/'etc/cse-trust/ca-bundle.pem';empty=base/'etc/cse-trust/empty-ca-dir'
    if not bundle.is_file() or not empty.is_dir():
        raise RuntimeError('The managed CA bundle/empty CA directory used by apply is unavailable; inspect trust before diagnosing package access')
    for key in ('CONDA_SSL_VERIFY','REQUESTS_CA_BUNDLE','SSL_CERT_FILE','CURL_CA_BUNDLE','PIP_CERT'):env[key]=str(bundle)
    if any(empty.iterdir()):raise RuntimeError('Expected dedicated empty CA directory')
    env['SSL_CERT_DIR']=str(empty)
    command=[str(base/'bin/python'),'-I','-B','-c',CONFLICT_DIAGNOSTIC]+argv
    finished=threading.Event();started=time.monotonic()
    def progress():
        while not finished.wait(30):print('Still diagnosing dependencies (%ds elapsed)'%(time.monotonic()-started),flush=True)
    heartbeat=threading.Thread(target=progress,daemon=True);heartbeat.start()
    print('Running the saved request with the same pins and strict channel priority; diagnostic limit 120 seconds.',flush=True)
    try:
        result=subprocess.run(command,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=120)
        stdout,stderr,code=result.stdout,result.stderr,result.returncode
    except subprocess.TimeoutExpired as exc:
        def decoded(value):return value.decode(errors='replace') if isinstance(value,bytes) else (value or '')
        stdout,stderr,code=decoded(exc.stdout),decoded(exc.stderr)+'\nConflict diagnostics timed out after 120 seconds.',None
    except OSError as exc:
        stdout,stderr,code='',type(exc).__name__+': '+str(exc),None
    finally:finished.set();heartbeat.join()
    report=directory/('solver-diagnostic-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.json')
    payload={'argv':[str(base/'bin/conda')]+argv,'phase':record.get('phase'),'returncode':code,
             'stdout':stdout,'stderr':stderr,'prefix_access':access_snapshot(prefix),'dry_run':True}
    fd=os.open(str(report),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as stream:json.dump(payload,stream,indent=2)
    try:
        data=json.loads(stdout)
        if not isinstance(data,dict):raise ValueError('Expected JSON object')
        message=data.get('message') or diagnostic_text(stdout,stderr)
    except ValueError:
        data={};message=diagnostic_text(stdout,stderr)
    print(str(message)[:16000],flush=True)
    print('Full diagnostic: '+str(report),flush=True)
    solved=code==0 and data.get('success') is True
    print('Result: '+('dry-run plan solved; no upgrade installed' if solved else 'solve/access failure; no package transaction attempted'))
    return 0 if solved else 2


def access_snapshot(path):
    """Read current access metadata; never chmod to make a check pass."""
    p = Path(os.path.abspath(os.path.expanduser(str(path))))
    result = dict(path=str(p),captured_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),**path_owner(p))
    try:
        st = p.lstat()
        result.update(mode=stat.filemode(st.st_mode),octal='%04o'%stat.S_IMODE(st.st_mode),
                      symlink_target=str(p.resolve()) if stat.S_ISLNK(st.st_mode) else None)
        result['access'] = {name:os.access(str(p),flag) for name,flag in
                            (('read',os.R_OK),('write',os.W_OK),('execute_or_traverse',os.X_OK))}
        try:
            result['extended_acl'] = 'system.posix_acl_access' in os.listxattr(str(p)) if hasattr(os,'listxattr') else 'unknown'
        except OSError as exc: result['extended_acl'] = 'unreadable: '+str(exc)
    except OSError as exc: result['stat_error'] = str(exc)
    result['blocked_parents'] = []
    for parent in p.parents:
        if not os.access(str(parent),os.X_OK):
            result['blocked_parents'].append(dict(path=str(parent),**path_owner(parent)))
    return result


def denied_paths(text):
    found = []
    patterns = (r"[Pp]ermission denied:?\s*['\"]([^'\"]+)['\"]",
                r"[Pp]ermission denied:?\s*(/[^\n|]+)",
                r"(?:path|filename)\s*[:=]\s*['\"](/[^'\"]+)['\"]",
                r"(?:path|filename)\s*:\s*(/[^\n|]+)")
    for pattern in patterns:
        for value in re.findall(pattern,text):
            value=value.strip().rstrip('.')
            if value.startswith('/') and value not in found:found.append(value)
    return found


def print_access(snapshot, say):
    say('  Path access snapshot: %s | owner=%s group=%s mode=%s | %s | ACL=%s' % (
        snapshot['path'],snapshot['owner'],snapshot['group'],snapshot.get('mode','unknown'),
        snapshot.get('access',snapshot.get('stat_error','unknown')),snapshot.get('extended_acl','unknown')))
    for parent in snapshot['blocked_parents']:
        say('    Parent not traversable by current account: %s | owner=%s group=%s' % (parent['path'],parent['owner'],parent['group']))


def forbidden_channel(value):
    value = str(value).strip().rstrip('/')
    denied=('defaults','anaconda','pkgs/main','pkgs/r','pkgs/free','pkgs/pro','pkgs/msys2')
    if any(value.lower()==name or value.lower().startswith(name+'/') for name in denied): return True
    parsed = urlsplit(value)
    return parsed.hostname in ('repo.anaconda.com','repo.continuum.io') or (
        parsed.hostname=='conda.anaconda.org' and parsed.path.strip('/').split('/')[0]=='anaconda')


def invalid_channel_reason(value):
    value=str(value or '').strip()
    if not value or value.lower() in ('none','null','<unknown>','unknown'):
        return 'missing channel name'
    if value.split('/',1)[0].lower() in ('none','null','<unknown>','unknown'):
        return 'placeholder value is not a channel name'
    if value.startswith(('Channel(', '{', '[')) or ('::' in value and '://' not in value) or any(c.isspace() for c in value):
        return 'channel is a representation or package spec rather than a channel name/URL'
    if value.rstrip('/') in ('conda.anaconda.org','anaconda.org','www.anaconda.org'):
        return 'public channel host has no channel name'
    if '://' in value:
        parsed=urlsplit(value)
        if parsed.scheme not in ('http','https','file'):
            return 'unsupported channel URL scheme'
        if parsed.scheme!='file' and not parsed.hostname:
            return 'channel URL has no hostname'
        path=[part for part in parsed.path.split('/') if part]
        if parsed.hostname in ('conda.anaconda.org','anaconda.org','www.anaconda.org'):
            if path[:1]==['t']:path=path[2:]
            if not path or is_channel_subdir(path[0]) or path[0] in ('label','None','null'):
                return 'public channel URL has no channel name (expected /conda-forge or another channel)'
        if parsed.path.endswith(('.conda','.tar.bz2','.whl')):
            return 'package archive URL is not a channel root'
    return None


def is_channel_subdir(value):
    return bool(re.fullmatch(r'(?:noarch|linux-[\w]+|osx-[\w]+|win-[\w]+|freebsd-[\w]+|zos-[\w]+)',str(value)))


def channel_value_url(value):
    """Conda config JSON can serialize Channel values as objects, not strings.

    A blank name is valid for channel_alias (a base location), whereas a full
    public channel still needs a name. Validation belongs to the calling context.
    """
    if isinstance(value,str):return value.strip().rstrip('/')
    if not isinstance(value,dict):return None
    if value.get('base_url'):
        return channel_value_url(value['base_url'])
    scheme=str(value.get('scheme') or 'https')
    location=str(value.get('location') or '').strip().rstrip('/')
    name=str(value.get('name') or '').strip().strip('/')
    if not location:
        if scheme=='file' and name:return 'file:///'+name
        return name if '://' in name else None
    base=location if '://' in location else scheme+'://'+location
    parsed=urlsplit(base)
    netloc=parsed.netloc
    auth=value.get('auth')
    if auth and '@' not in netloc:netloc=str(auth)+'@'+netloc
    parts=[parsed.path.rstrip('/')]
    token=value.get('token')
    if token:parts.extend(('t',str(token).strip('/')))
    if name:parts.append(name)
    path='/'.join(part.strip('/') for part in parts if part)
    return urlunsplit((parsed.scheme,netloc,('/'+path) if path else '',parsed.query,parsed.fragment))


def requested_channels(extras, config):
    """Resolve the explicit allowlist locally, so Anaconda defaults cannot hide in aliases."""
    custom = config.get('custom_channels') or {}
    multi = config.get('custom_multichannels') or {}
    alias = config.get('channel_alias') or 'https://conda.anaconda.org'
    def resolve(name,seen=()):
        name=channel_value_url(name) if isinstance(name,dict) else str(name).strip()
        if not name:raise RuntimeError('Invalid requested channel object: missing location/name')
        problem=invalid_channel_reason(name)
        if problem:raise RuntimeError('Invalid requested channel %r: %s'%(name,problem))
        if forbidden_channel(name): raise RuntimeError('Anaconda defaults channel is excluded: '+str(name))
        if name in seen: raise RuntimeError('Recursive channel alias: '+name)
        if name in multi:
            urls=[]
            for child in multi[name]: urls.extend(resolve(child,seen+(name,)))
            return urls
        if '://' in name:
            urls=[name.rstrip('/')]
        elif name.startswith('/'):
            urls=[Path(name).as_uri()]
        else:
            # custom_channels maps a channel name to the base location, without
            # that channel name (the conda configuration contract).
            key=next((k for k in sorted(custom,key=len,reverse=True) if name==k or name.startswith(k+'/')),None)
            configured=custom[key] if key else alias
            location=channel_value_url(configured)
            if not location or '://' not in location:
                raise RuntimeError('Invalid channel alias/custom location for %r: cannot resolve its URL from the configuration value'%(name,))
            if key and isinstance(configured,dict) and (configured.get('name') or configured.get('base_url')):
                # Resolved custom Channel objects already include their name.
                # Raw .condarc custom-channel strings contain only the location.
                urls=[location.rstrip('/')+name[len(key):]]
            else:
                urls=[location.rstrip('/')+'/'+name]
        for url in urls:
            problem=invalid_channel_reason(url)
            if problem:raise RuntimeError('Invalid resolved channel %r: %s'%(url,problem))
            if forbidden_channel(url): raise RuntimeError('Channel resolves to excluded Anaconda defaults: '+url)
        return urls
    names=list(dict.fromkeys(['conda-forge']+list(extras)))
    urls=list(dict.fromkeys(url for name in names for url in resolve(name)))
    if not urls:raise RuntimeError('Requested channels resolved to an empty channel set')
    for pin in config.get('pinned_packages') or []:
        if '::' in pin:
            origin=pin.split('::',1)[0]
            if origin not in names and origin.rstrip('/') not in urls:
                if any(url not in urls for url in resolve(origin)):
                    raise RuntimeError('Channel-qualified pin is outside requested channels: '+pin)
    # Retain the legacy command shape for the ordinary conda-forge mapping.
    flags = CHANNEL_ARGS if not extras and urls==['https://conda.anaconda.org/conda-forge'] else (
        ['--override-channels']+[x for url in urls for x in ('--channel',url)]+['--strict-channel-priority'])
    return names,urls,flags


def recorded_origin(record):
    """Normalize installed sources; fall back to archive URL if the channel is unusable."""
    missing={'','<unknown>','unknown','none','null','@','pypi','pypi_0'}
    channel=record.get('channel')
    if isinstance(channel,dict): channel=channel_value_url(channel)
    for candidate in (channel,record.get('url')):
        value=str(candidate or '').strip()
        if value.lower() in missing or (value.startswith('<') and value.endswith('>')):continue
        if value.startswith(('conda.anaconda.org/','anaconda.org/')):value='https://'+value
        if urlsplit(value).path.endswith('.whl'):continue
        if '://' in value:
            parsed=urlsplit(value)
            path=parsed.path.rstrip('/')
            if path.endswith(('.conda','.tar.bz2')):path=path.rsplit('/',1)[0]
            # Only strip real platform names. Malformed subdir metadata must not
            # strip the actual channel name (e.g. subdir='conda-forge').
            if is_channel_subdir(path.rsplit('/',1)[-1]):path=path.rsplit('/',1)[0]
            value=urlunsplit((parsed.scheme,parsed.netloc,path,'',''))
        else:
            value=value.rstrip('/')
            if '/' in value and is_channel_subdir(value.rsplit('/',1)[-1]):value=value.rsplit('/',1)[0]
        if not invalid_channel_reason(value):return value
    return None


def environment_channels(meta, extras, config):
    config_without_pins={k:v for k,v in config.items() if k!='pinned_packages'}
    origins, excluded, unknown={},[],[]
    for name,record in sorted(meta.items()):
        origin=recorded_origin(record)
        if not origin:
            unknown.append(name);continue
        # Check both fields: an innocent channel label must not mask a forbidden URL.
        if forbidden_channel(origin) or (record.get('url') and forbidden_channel(record['url'])):
            excluded.append({'package':name,'source':origin,'reason':'Anaconda defaults source excluded'});continue
        try:
            _,resolved,_=requested_channels([origin],config_without_pins)
        except RuntimeError as exc:
            excluded.append({'package':name,'source':origin,'reason':str(exc)});continue
        fallback=requested_channels([],config_without_pins)[1]
        # Resolving an origin also includes the common fallback. Preserve a single
        # origin, rather than guessing which member of a multichannel supplied it.
        candidates=[url for url in resolved if url not in fallback]
        if not candidates and origin in ('conda-forge',)+tuple(fallback): candidates=fallback
        if len(candidates)!=1:
            unknown.append(name);continue
        origins[name]=candidates[0]
    inferred=list(dict.fromkeys(origins.values()))
    names,urls,flags=requested_channels(list(extras)+inferred,config)
    return names,urls,flags,origins,excluded,unknown


def qualify_specs(specs,origins):
    output=[]
    for spec in specs:
        name=re.split(r'[<>=!~ ]',spec,1)[0]
        output.append(origins[name]+'::'+spec if name in origins else spec)
    return output


def allowed_pin_origin(origin,names,urls,config):
    if origin in names or origin.rstrip('/') in urls:return True
    try:
        _,resolved,_=requested_channels([origin],{k:v for k,v in config.items() if k!='pinned_packages'})
        return all(url in urls for url in resolved)
    except RuntimeError:return False


def inspect_trust(base, prefixes=()):
    print('READ-ONLY CERTIFICATE CHECK | base: '+str(base))
    bundle=base/'etc/cse-trust/ca-bundle.pem'
    good=False
    paths=[bundle]
    for prefix in dict.fromkeys([base]+list(prefixes)):
        print('Prefix: '+str(prefix)+(' [BASE]' if prefix==base else ''))
        try:
            meta=records(prefix)
            for n in ('ca-certificates','certifi','pip'):
                if n in meta:
                    try: status='MEETS SCRIPT MINIMUM' if version(meta[n]['version'])>=version(MINIMUM[n]) else 'BELOW SCRIPT MINIMUM '+MINIMUM[n]
                    except RuntimeError: status='version needs review'
                    print('  Package: %s=%s | %s'%(n,meta[n]['version'],status))
        except (OSError,ValueError,KeyError) as exc: print('  Package inventory unavailable: '+str(exc))
        paths.extend(prefix/rel for rel in ('ssl/cert.pem','ssl/cacert.pem'))
        paths.extend(prefix.glob('lib/python*/site-packages/certifi/cacert.pem'))
        paths.extend(prefix.glob('lib/python*/site-packages/pip/_vendor/certifi/cacert.pem'))
        condarc=prefix/'.condarc'
        try:
            matches=re.findall(r'(?m)^ssl_verify\s*:\s*(.*)$',condarc.read_text())
            print('  Prefix ssl_verify setting (raw): '+('; '.join(matches) or 'no top-level setting'))
        except FileNotFoundError: print('  Prefix .condarc: absent (no local override; inherited configuration may apply)')
        except OSError as exc: print('  Prefix .condarc: '+str(exc))
        try:
            state=json.loads((prefix/'conda-meta/state').read_text())
            print('  Activation CA variables: '+json.dumps({k:v for k,v in state.get('env_vars',{}).items() if k in ('CONDA_SSL_VERIFY','REQUESTS_CA_BUNDLE','SSL_CERT_FILE','CURL_CA_BUNDLE','PIP_CERT','SSL_CERT_DIR')},sort_keys=True))
        except FileNotFoundError: print('  Activation state: absent')
        except (OSError,ValueError) as exc: print('  Activation state: '+str(exc))
    for path in dict.fromkeys(paths):
        try:
            data=path.read_bytes();entries=pem_entries(data.decode())
            present=[ROOTS[h] for h,pem in entries if h in ROOTS]
            print('Bundle: %s\n  SHA256=%s\n  Certificates=%d; known incident roots=%s' % (path,hashlib.sha256(data).hexdigest(),len(entries),', '.join(present) or 'NONE OF THE FOUR MATCHED'))
            if path==bundle: good=not present
        except FileNotFoundError:
            if path==bundle: print('CSE managed bundle: ABSENT at '+str(path))
        except (OSError,ValueError,RuntimeError) as exc:
            print('Bundle check failed: %s | %s'%(path,exc))
            if isinstance(exc,PermissionError):print_access(access_snapshot(path),print)
    marker=base/'etc/cse-trust/managed-by-patch-miniforge-trust'
    try: print('Managed marker: '+marker.read_text().strip())
    except OSError as exc: print('Managed marker unavailable: '+str(exc))
    print('Current shell CA variables: '+json.dumps({k:os.environ[k] for k in ('CONDA_SSL_VERIFY','REQUESTS_CA_BUNDLE','SSL_CERT_FILE','CURL_CA_BUNDLE','PIP_CERT','SSL_CERT_DIR') if k in os.environ},sort_keys=True))
    selected=[k for k in ('CONDA_SSL_VERIFY','REQUESTS_CA_BUNDLE','SSL_CERT_FILE','CURL_CA_BUNDLE','PIP_CERT') if os.environ.get(k)==str(bundle)]
    print('Current shell variables selecting CSE copy: '+(', '.join(selected) or 'NONE; application-specific configuration may still apply'))
    print('CSE bundle screening: '+('PRESENT, PARSEABLE, FOUR KNOWN ROOTS ABSENT' if good else 'NOT CONFIRMED'))
    print('Stored bundle, package versions and active application trust are separate. This does not prove full chain rejection or proxy remediation.')
    print('No changes, package updates or external TLS connections were made.')
    return 0 if good else 2


def main():
    ap = argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('miniforge', nargs='?', type=Path)
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--inspect-trust',action='store_true',help='Read actual CSE/base CA files and configuration; no updates')
    ap.add_argument('--trust-only',action='store_true',help='Only prepare/write the CSE bundle and shell snippet; no package/environment permission changes')
    scope=ap.add_mutually_exclusive_group()
    scope.add_argument('--base-only',action='store_true',help='Select only the loaded base; bootstrap older conda before the full update')
    scope.add_argument('--only',type=Path,action='append',default=[],help='Select only this exact environment; repeatable; still uses the base conda/CSE bundle')
    scope.add_argument('--all-envs',action='store_true',help='Opt into discovery and maintenance of all eligible environments; default is base only')
    ap.add_argument('--channel',action='append',default=[],help='Additional approved community channel or mirror; repeatable; Anaconda defaults excluded')
    ap.add_argument('--report',type=Path,metavar='LOG_DIR_OR_latest',help='Read an existing summary/run.log and explain failures; no updates, group checks or network')
    ap.add_argument('--diagnose',type=Path,metavar='LOG_DIR_OR_latest',help='Repeat the saved failed solve as a dry run with detailed conflicts and access checks; may refresh repodata')
    ap.add_argument('--verbose',action='store_true',help='Show per-path permission details and subprocess commands; full details are always logged')
    ap.add_argument('--offline', action='store_true',help='Apply using cache/file channels; never retrieve online')
    ap.add_argument('--upgrade-conda',action='store_true',help='Also upgrade conda in non-base prefixes; base updates conda automatically')
    ap.add_argument('--ca-bundle',type=Path,help='Source site PEM; default detect from conda/current configuration')
    ap.add_argument('--extra-ca',type=Path,action='append',default=[])
    ap.add_argument('--include',type=Path,action='append',default=[])
    ap.add_argument('--exclude',type=Path,action='append',default=[])
    ap.add_argument('--scan-root',type=Path,action='append',default=[])
    ap.add_argument('--chains-dir',type=Path,help='Approved local incident chain directory; no downloads')
    ap.add_argument('--log-dir',type=Path)
    args = ap.parse_args()
    if (args.include or args.scan_root) and not args.all_envs:
        ap.error('--include and --scan-root require --all-envs; use --only for exact prefixes')
    if args.diagnose:
        if args.apply or args.report or args.inspect_trust or args.trust_only:
            ap.error('--diagnose cannot be combined with apply/report/trust modes')
        return diagnose_existing(args.diagnose,find_base(args.miniforge,safe_environment()),args.offline)
    if args.report:
        if args.apply or args.inspect_trust or args.trust_only: ap.error('--report cannot be combined with apply/trust modes')
        return report_existing(args.report,args.verbose)
    if args.inspect_trust:
        if args.apply or args.trust_only: ap.error('--inspect-trust cannot be combined with --apply/--trust-only')
        base=find_base(args.miniforge,safe_environment())
        return inspect_trust(base,[p.expanduser().resolve() for p in args.only])
    if os.geteuid() == 0: ap.error('Run as the software maintenance account, not root')
    cse_gid = maintenance_gid()  # validate before any deployment changes
    os.umask(0o002)
    env = safe_environment()
    base = find_base(args.miniforge,env); conda = base/'bin/conda'
    if not maintainable(base): raise RuntimeError('No user/group maintenance access to base')
    if args.trust_only and not args.ca_bundle: ap.error('--trust-only requires --ca-bundle with your approved CSE PEM source')
    config = {} if args.trust_only else json.loads(capture([conda,'config','--show','--json'],env))
    channel_names,channel_urls,channel_args = requested_channels(args.channel,{k:v for k,v in config.items() if k!='pinned_packages'})
    source = choose_source(args,config,base)
    bundle_text, removed = filtered_bundle([source] + args.extra_ca)
    skipped_paths = []
    if args.trust_only or (not args.all_envs and not args.only): prefixes=[base]
    elif args.only: prefixes=list(dict.fromkeys(p.expanduser().resolve() for p in args.only))
    else: prefixes=discover(base,conda,env,args.include,args.scan_root,args.exclude,skipped_paths)
    exclusions=[p.expanduser().resolve() for p in args.exclude]
    prefixes=[p for p in prefixes if not any(p==x or x in p.parents for x in exclusions)]
    if not prefixes: raise RuntimeError('No prefixes selected after exclusions')
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
    say('Classic solver: detailed conflict hints disabled to avoid the upstream set/tuple reporting crash; incompatible plans remain rejected.')
    say('Fallback/explicit package channels: '+', '.join(channel_names)+'; Anaconda defaults excluded; external plugins disabled; no PyPI fallback')
    say('Resolved channel URLs: '+', '.join(channel_urls))
    say('Scope: '+('CSE trust files only' if args.trust_only else ', '.join(str(p)+(' [BASE]' if p==base else '') for p in prefixes)))
    say('Base: '+str(base)); say('Source CA: '+str(source));say('Private logs: '+str(logdir))
    say('Current UID/groups: %s / %s' % (os.geteuid(),','.join(map(str,sorted(groups())))))
    say('Shared permissions target: cse (GID %d); directories 2775, files 0664, executables 0775' % cse_gid)
    say('Source roots selected for removal from CSE copy: '+(', '.join(removed) or 'none of the four matched'))
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
        event['access_details']=[access_snapshot(p) for p in denied_paths(diagnostic)]
        (logdir/filename).write_text(json.dumps(dict(event,argv=list(map(str,cmd)),stdout=stdout,stderr=stderr),indent=2))
        row.setdefault('command_failures',[]).append(event)
        return RuntimeError('Command failed during %s (exit %s): %s | %s | full output: %s' %
                            (event['phase'],code,display[:180],diagnostic,logdir/filename))
    def run(cmd, allow_failure=False):
        detail('$ '+shlex.join(map(str,cmd)))
        phase=row.get('phase','local command')
        say('Running: '+phase)
        finished=threading.Event()
        started=time.monotonic()
        def progress():
            while not finished.wait(30):
                say('Still running: %s (%ds elapsed)'%(phase,time.monotonic()-started))
        heartbeat=threading.Thread(target=progress,daemon=True)
        heartbeat.start()
        try:
            r = subprocess.run(list(map(str,cmd)),env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        except OSError as exc:
            raise record_failure(cmd,'',str(exc),None, str(exc)+(' | filename: '+repr(exc.filename) if exc.filename else '')) from exc
        finally:
            finished.set()
            heartbeat.join()
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
        if isinstance(data,dict) and data.get('dry_run') and 'install' in cmd and '--dry-run' not in cmd:
            raise record_failure(cmd,r.stdout,r.stderr,r.returncode,
                                 'Conda returned a dry-run result for an install command; no installed upgrade is confirmed')
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
    certificate_status={'status':'written' if args.apply else 'planned','bundle':str(bundle),'source':str(source),'roots_selected_for_removal':removed,
                        'sha256':hashlib.sha256(bundle.read_bytes()).hexdigest() if args.apply else None,
                        'activation':'shell snippet available; each application/environment must use it; OS/proxy unchanged'}
    (logdir/'certificate-status.json').write_text(json.dumps(certificate_status,indent=2))
    say('CSE certificate stage: '+certificate_status['status'].upper()+' | '+str(bundle))
    say('Certificate preparation reads the source into one shared CSE copy. Only selected prefixes receive package/configuration updates; their package-owned PEMs may be replaced by conda.')
    if args.apply: say('CSE bundle SHA256: '+certificate_status['sha256'])
    if args.trust_only:
        say('No package updates or environment permission normalization attempted.')
        say('Existing CA packages/embedded bundles remain separate update work.')
        if args.apply: say('For the current shell after loading your module: . '+shlex.quote(str(trustdir/'use-ca.sh')))
        say('Certificate stage report: '+str(logdir/'certificate-status.json'))
        log.close()
        if lockfile: lockfile.close()
        return 0
    for i,prefix in enumerate(prefixes):
        row = {'prefix':str(prefix),'status':'incomplete','issues':[],'skipped_paths':[],'changes_started':False,'ownership':path_owner(prefix)};results.append(row)
        say('\nPrefix: '+str(prefix)+(' [BASE]' if prefix==base else ''))
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
            initial_meta = meta
            row['installed_channels']=sorted({str(r.get('channel') or r.get('url') or 'unknown') for r in meta.values()})
            channel_names,channel_urls,channel_args,origins,excluded_origins,unknown_origins=environment_channels(meta,args.channel,config)
            row['requested_channels']=channel_urls
            row['package_origins']=origins
            row['excluded_installed_sources']=excluded_origins
            row['unknown_package_origins']=unknown_origins
            say('Environment channels from installed records: '+', '.join(channel_urls))
            if excluded_origins:say('Excluded Anaconda/default sources: '+', '.join(sorted({r['source'] for r in excluded_origins})))
            channel_records=[{'package':n,'recorded_channel':r.get('channel'),'recorded_url':r.get('url'),'recorded_subdir':r.get('subdir'),'normalized_origin':recorded_origin(r),'selected_origin':origins.get(n)} for n,r in sorted(meta.items())]
            channel_report=logdir/('%03d-channel-records.json'%i)
            channel_report.write_text(json.dumps(channel_records,indent=2))
            row['channel_records_file']=str(channel_report)
            if unknown_origins:
                say('No usable channel origin for %d package(s); no malformed source added. Fallback/explicit channels apply. Details: %s'%(len(unknown_origins),channel_report))
                detail('Unknown/non-channel package origins (no source inferred): '+', '.join(unknown_origins))
            for pinfile in (prefix/'conda-meta/pinned',):
                if pinfile.is_file():
                    for pin in pinfile.read_text().splitlines():
                        pin=pin.split('#',1)[0].strip()
                        if '::' in pin and not allowed_pin_origin(pin.split('::',1)[0],channel_names,channel_urls,config):
                            raise RuntimeError('Channel-qualified prefix pin outside requested channels: '+pin)
            broad = prefix == base
            upgrade_conda = args.upgrade_conda or broad
            row['package_policy']='all base packages may update' if broad else 'targeted maintenance; application packages pinned'
            say('Package policy: '+row['package_policy'])
            if broad:
                row['conda_bootstrap']=conda_bootstrap_status(meta)
                say('Conda bootstrap: '+row['conda_bootstrap']['status']+
                    ' | current='+str(row['conda_bootstrap']['before'])+' | minimum='+CONDA_MINIMUM)
            targets,allowed,specs = plan_specs(meta,upgrade_conda,broad=broad)
            specs=qualify_specs(specs,origins)
            row['package_targets'] = [{'name':n,'current':meta[n]['version'],'request':('>='+MINIMUM[n] if n in MINIMUM else ('>='+CONDA_MINIMUM if n == 'conda' else 'compatible build from installed source')),'source':origins.get(n,'fallback/explicit allowed channels')} for n in sorted(targets)]
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
                if not broad and 'pip' in audit['packages'] and audit['python'] < [3,10] and version(audit['packages']['pip']) < version(MINIMUM['pip']):
                    row['issues'].append('Old pip on Python <3.10 needs a reviewed compatible remediation')
            if args.apply:
                if row['issues']: raise RuntimeError('Package review required; no package/configuration/permission changes attempted for this prefix')
                row['phase'] = 'save configuration and conda package inventory'
                for relative in ('.condarc','conda-meta/state','conda-meta/history'):
                    p=prefix/relative
                    if p.is_file(): (logdir/('%03d-before-'%i+relative.replace('/','_'))).write_bytes(p.read_bytes())
                (logdir/('%03d-before-explicit.txt'%i)).write_text(run([conda,'list','-p',prefix,'--explicit']).stdout)
                if broad:
                    meta=bootstrap_conda(base,meta,channel_args,origins,args.channel,config,
                                         args.offline,runjson,logdir,row,say)
                    # The next solve must use the updated installed records, not
                    # exact pins for the older manager we just replaced.
                    _,_,channel_args,origins,_,_=environment_channels(meta,args.channel,config)
                    conda_minimum=row['conda_bootstrap'].get('target',CONDA_MINIMUM)
                    targets,allowed,specs=plan_specs(meta,upgrade_conda,broad=True,conda_minimum=conda_minimum)
                    specs=qualify_specs(specs,origins)
                if targets:
                    row['phase'] = 'solve package update (dry run)'
                    cmd=[conda,'install','-p',prefix,'--solver','classic','--json']+(['--update-all'] if broad else ['--freeze-installed'])+channel_args+specs
                    if args.offline: cmd.append('--offline')
                    plan=runjson(cmd+['--dry-run'])
                    (logdir/('%03d-plan.json'%i)).write_text(json.dumps(plan,indent=2))
                    changed=check_plan(plan,allowed)
                    row['package_plan'] = [{'name':r['name'],'before':meta.get(r['name'],{}).get('version','absent'),'after':r['version'],'build':r.get('build_string') or r.get('build')} for r in plan.get('actions',{}).get('LINK',[])]
                    detail('Validated package changes: '+(', '.join(changed) or 'none'))
                    # Lock the planned final versions/builds before the execution solve.
                    final,exact=exact_plan_specs(meta,plan,origins,args.channel,config)
                    verify_minimums(meta,{n:{'version':v} for n,(v,b) in final.items()},upgrade_conda,
                                    row.get('conda_bootstrap',{}).get('target',CONDA_MINIMUM))
                    execution=[conda,'install','-p',prefix,'--solver','classic','--json','--yes']+([] if broad else ['--freeze-installed'])+channel_args+exact
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
                row['package_changes'] = [{'name':n,'before':initial_meta.get(n,{}).get('version','absent'),'after':r['version']} for n,r in sorted(after_meta.items()) if n not in initial_meta or (r['version'],r['build']) != (initial_meta[n]['version'],initial_meta[n]['build'])]
                row['trust_configuration'] = 'configured to use'
                row['security_verification']=verify_minimums(meta,after_meta,upgrade_conda,
                                                           row.get('conda_bootstrap',{}).get('target',CONDA_MINIMUM))
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
            if exc.filename: row['access_details']=[access_snapshot(exc.filename)]
            skipped_paths.append({'path':str(exc.filename or prefix),'stage':'environment','reason':str(exc),'prefix':str(prefix)})
            log.write(traceback.format_exc())
        except Exception as exc:
            row['issues'].append(str(exc));log.write(traceback.format_exc())
        for issue in row['issues']:say('ATTENTION: '+issue)
        say('Status: '+row['status'])
    (logdir/'summary.json').write_text(json.dumps(results,indent=2))
    skipped_paths = write_skip_reports(logdir,skipped_paths)
    final_summary(results,args.apply,bundle,say)
    say('CSE certificate stage: '+certificate_status['status'].upper()+'; see '+str(logdir/'certificate-status.json'))
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
