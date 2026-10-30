#!/usr/bin/env python3
"""CSE Miniforge certificate maintenance, revision 31 (2026-10-30).

Python 3.8+, standard library. Run as a maintenance account, not root.
  python3 patch_miniforge_trust.py --base-guide          # ordered team rollout guide
  python3 patch_miniforge_trust.py --repair-curl          # targeted curl/libcurl plan
  python3 patch_miniforge_trust.py --repair-curl --apply  # install pair and verify
  python3 patch_miniforge_trust.py --export-changes /path/to/run --changes-output /new/user-notes
  python3 patch_miniforge_trust.py                       # preview loaded install
  python3 patch_miniforge_trust.py --check-permissions   # read-only, all known blockers
  python3 patch_miniforge_trust.py /path/to/miniforge     # explicit install
  python3 patch_miniforge_trust.py --apply               # apply, approved channels
  python3 patch_miniforge_trust.py --stage ~/cse-candidate # build privately; review before changing base
  python3 patch_miniforge_trust.py --stage ~/cse-retry --stage-skip PACKAGE
  python3 patch_miniforge_trust.py --promote ~/cse-candidate        # dry-run reviewed set
  python3 patch_miniforge_trust.py --promote ~/cse-candidate --apply
  python3 patch_miniforge_trust.py --apply --offline     # approved cached packages
  python3 patch_miniforge_trust.py --apply --upgrade-conda
  python3 patch_miniforge_trust.py --report latest        # explain saved logs only
  python3 patch_miniforge_trust.py --diagnose latest      # dry-run failed solve with conflict details and access checks
  python3 patch_miniforge_trust.py --inspect-trust        # inspect actual CA files
  python3 patch_miniforge_trust.py --base-only            # preview base only
  python3 patch_miniforge_trust.py --only /path/to/env    # preview one prefix
  python3 patch_miniforge_trust.py --all-envs             # opt into discovery
  python3 patch_miniforge_trust.py --trust-only --apply   # existing native PEMs only
  python3 patch_miniforge_trust.py --verify-user ~/cse-user-check-1 # online private user checks

No incident test-site connections, remote execution or OS writes.
--verify-user NEW_PRIVATE_DIR explicitly exercises HTTPS package downloads,
private environment creation, activation, imports, a local pip wheel build and
user write access. It changes only that new private directory, requires no cse
membership and makes no base updates. It preserves the loaded TLS settings;
insecure settings or known incident roots fail before package downloads. Optional
--chains-dir checks supplied incident chains offline. Reports cover this account
and these exercises, not every user, application, compiler or proxy trust policy.
Default preview is local-only: inventory, CA inspection, ownership and permissions.
--promote previews are dependency dry runs of a reviewed set; --apply installs it
at its original base prefix after freshness/access checks. Stage each system
separately after loading that site's environment and Miniforge.
Apply reuses non-default channels recorded in each environment's installed conda
packages. Non-base requests preserve per-package sources; base uses channel priority. conda-forge remains a
fallback; --channel adds an explicit community channel/mirror when metadata is absent. Anaconda defaults/repo.anaconda.com sources are excluded.
All solves use --override-channels and strict channel priority.
There is no PyPI/pip-install fallback. Solver subprocesses discover no external
plugins and explicitly enable only the installed libmamba solver hook.
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
Final summaries repeat retained package requests, removals, permission counts and failure reasons.
Per-owner skip reports are private review aids. A skip is not protection.
--stage NEW_PRIVATE_DIR is a separate workflow: it solves and installs a fresh
candidate with its own cache/trust files and writes version/build comparisons.
The source base stays read only, including its caches and permissions. No shared
maintenance access or cse membership is required for staging. --stage-skip NAME
explicitly omits an application request; dependencies may still require it.
Failed solves/installations retain honest failure reports. Staging performs no
promotion to base; review the candidate before deciding on any live update.
--report LOG_DIR (or latest) reads prior summaries/logs without updates or network.
New command failures save separate JSON records with arguments, exit status, phase
and stdout/stderr; final summaries include the underlying error rather than a wrapper.

Default package targets: existing ca-certificates>=2026.10.19 (conda-forge),
certifi>=2026.10.19, pip>=26.2.2, uv>=0.13.4, and sigstore>=4.5.1 where
installed through conda. Base also requests conda>=26.9.4 where installed;
--upgrade-conda requests that minimum in non-base prefixes.
The existing Miniforge distribution/prefix is kept. No installer is downloaded,
replaced or rerun. Apply uses the installed libmamba solver with entry-point
plugin discovery disabled and only its solver hook explicitly enabled. PyPI
integration plugins are not enabled. A missing/broken solver fails before updates.
Base Conda, Python, solver packages, NumPy, Jupyter, Boost and other installed base
applications update compatibly in ONE transaction. Retained requests come from
explicit history and the installed dependency graph, not a mandatory request for
every old dependency. The solve uses --update-all --prune, security minimums and
approved channel priority, without historical per-package source locks. All base
package pins are ignored with --no-pin, including prefix pin files and
pinned_packages settings. Python and applications can update together; unused
dependencies may leave. Stored pin/configuration files and the Miniforge/module/
Spack release selection are retained. Non-base prefixes keep their pin policy.
Base preflight defers packages whose installed paths cannot be replaced with the
current access. Those packages receive temporary exact version/build holds and
are retained. Python's major/minor is constrained when needed for held Python
packages. The execution solver refuses any unlink/relink of held packages, even
the same build. Required security/Conda targets still apply; an incompatible hold
stops before installation. A successful run with holds is updated-with-skips and
lists deferred packages and paths. No stored pins are changed. Preflight cannot
prove future access, server policy or access to every incoming package path.
Known conda-forge boost/boost-cpp names migrate to libboost-python-devel and
libboost-devel, preserving development functionality. Unknown conflicts are not
treated as proof of deprecation. The exact validated versions/builds and removals
are installed and verified before configuring trust. There is no manager-only
bootstrap and no classic conflict-hint graph. Read-only planning is bounded at
180 seconds; an installation transaction is not killed by that planning limit.
Non-base prefixes retain Python/application version+build pins, source-qualified
requests and --freeze-installed. --offline uses cached packages/channel metadata.
The known XKB directory-to-symlink migration is checked against cached package
metadata. An old package-owned directory is preserved by rename in private
share/X11/.cse-trust-path-backups before installation. Untracked/shared files stop
the migration. Failed installations restore that tree when package records roll
back; partial rollback retains the backup and reports recovery paths. These
backups are excluded from permission normalization. This is not a full snapshot.
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
--trust-only is a separate native-file mode: filter the loaded base's existing
ssl and certifi PEM bundles in place. No --ca-bundle is required, no CSE copy or
shell snippet is created, and no package/configuration command is run. Existing
script-created CSE-path overrides in base configuration are redirected to its
native ssl PEM; unrelated settings are preserved. Already clean files are not
rewritten. Package updates can replace these PEM files; rerun this local check
afterward. Explicit --ca-bundle/--extra-ca sources add organizational certificates
to the existing bundles without writing to those source paths.
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
import ast
import csv
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
SCRIPT_REVISION = 31
BASE_ROLLOUT_GUIDE = """CSE MINIFORGE: TEAM BASE-ONLY ROLLOUT (revision 31)

Already updated and validated, but curl is missing while libcurl is installed?
Use the focused repair instead of repeating the rollout:
   python3 patch_miniforge_trust.py --repair-curl
   python3 patch_miniforge_trust.py --repair-curl --apply
It selects the newest stable curl advertised by approved conda-forge sources,
installs a matched curl/libcurl pair and necessary dependencies, keeps unrelated
applications/managers unchanged, filters native PEMs, normalizes permissions and
checks PATH, loaded libcurl and HTTPS. Preview first; conflicts stop for review.
Use the normal module setup; clear a cached system curl with hash -r or reload
the module. No Miniforge installer replacement or full restage is required.

Repeat separately for each distinct installation, including GCC and Intel.
Load that site's usual environment/compiler and Miniforge modules first.
The loaded module supplies the base path; no system name is required.
Use the maintenance account for shared changes, never root. Private staging and
user verification require no cse membership; promotion/native PEM edits do.

1. Choose a NEW private stage name under your home for this installation:
   cse_stage="$HOME/cse-base-review-1"
   python3 patch_miniforge_trust.py --stage "$cse_stage"

2. Review before changing base:
   python3 patch_miniforge_trust.py --report "$cse_stage"
   Read review.md and comparison.csv there; require ready-for-review, review
   changed/added/not-selected packages, and run the needed application checks
   in "$cse_stage/env". A successful solve is not full application validation.

3. Check all known installed/candidate permission blockers as the maintainer:
   python3 patch_miniforge_trust.py --check-permissions --promote "$cse_stage"
   Resolve reported owner/admin repairs and inspection gaps; rerun the check.
   This check reports access; it does not repair permissions automatically.

4. In the normal maintenance window, with snapshot/recovery arrangements and
   concurrent base updates/jobs stopped, validate and apply the reviewed set:
   python3 patch_miniforge_trust.py --promote "$cse_stage"
   python3 patch_miniforge_trust.py --promote "$cse_stage" --apply
   Stop on failure. Promotion uses the existing base path, verifies the accepted
   package set, and normalizes eligible base permissions to cse. Read its exact
   printed log directory with --report; review skips/updated-with-skips.

5. Filter the EXISTING base PEM files after package installation:
   python3 patch_miniforge_trust.py --trust-only
   python3 patch_miniforge_trust.py --trust-only --apply
   python3 patch_miniforge_trust.py --inspect-trust
   This removes four known incident-root fingerprints and redirects earlier
   script-created base CSE-path settings to the native PEM. No use-ca.sh step
   is needed for this sequence. Other site CAs/settings are preserved.

6. Verify user operations in a fresh shell with the same usual modules loaded,
   ideally as an ordinary user (choose a NEW private test name):
   python3 patch_miniforge_trust.py --verify-user "$HOME/cse-user-check-1"
   python3 patch_miniforge_trust.py --report "$HOME/cse-user-check-1"
   Require the requested checks to pass; read verification.md and its limits.
   Optional --chains-dir PATH checks supplied incident chains offline; without
   it, chain rejection is explicitly not-tested. No live incident sites are probed.

Keep the stage/reports, source commit, promoted-base logs and certificate/user
results per installation. Verified updates write NNN-user-changes/README.md,
packages.csv, packages.json and manifest.json beside the private logs. To export
an older run without accessing installed software:
   python3 patch_miniforge_trust.py --export-changes /path/to/promotion-log \\
     --changes-output "$HOME/miniforge-release-notes/base-update-1"
Review the evidence/coverage label, then copy only the generated files to the
approved user-readable docs location and link them from the updates index:
https://github.com/ray12514/compiler-hardening-trial/blob/main/docs/miniforge-updates/README.md
Candidate-only comparisons must not be published as completed changes.
Use a new stage if the source package/control state
changes; do not rerun a stale promotion to repair a later certificate/user check.
Old CSE exports in an existing shell need clearing or a fresh shell.
Do not use --all-envs/--only, delete old environments, replace Miniforge, or edit
admin trust files in this rollout. Other baseline environments are a later sweep.

Full handoff guide (script retrieval, review gates and recovery pointers):
https://github.com/ray12514/compiler-hardening-trial/blob/main/docs/miniforge-base-rollout.md
"""
BASE_REPLACEMENTS = {'boost':('libboost-python-devel',),'boost-cpp':('libboost-devel',)}
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
    for k in ('PYTHONPATH','PYTHONHOME','LD_PRELOAD','LD_LIBRARY_PATH','CSE_CONDA_PERMISSION_HOLDS','CSE_CONDA_APPROVED_PLAN',
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


def native_bundle_paths(base):
    """Resolve aliases only within the selected prefix, never into an OS store."""
    candidates=[base/rel for rel in ('ssl/cacert.pem','ssl/cert.pem')]
    candidates.extend(sorted(base.glob('lib/python*/site-packages/certifi/cacert.pem')))
    candidates.extend(sorted(base.glob('lib/python*/site-packages/pip/_vendor/certifi/cacert.pem')))
    paths=[]
    for candidate in candidates:
        if not candidate.exists() and not candidate.is_symlink(): continue
        target=candidate.resolve(strict=True)
        if base not in target.parents or any(base/part in target.parents for part in ('pkgs','envs')):
            raise RuntimeError('Refusing CA target outside the selected prefix: '+str(candidate)+' -> '+str(target))
        if not target.is_file(): raise RuntimeError('CA target is not a file: '+str(target))
        if target not in paths: paths.append(target)
    if not paths: raise RuntimeError('No existing Miniforge PEM bundles found under '+str(base))
    return paths


def replace_preserving_metadata(path, data):
    """Replace a regular target, preserving symlink aliases and detaching hardlinks."""
    st=path.stat()
    fd,temporary=tempfile.mkstemp(prefix='.cse-ca-',dir=str(path.parent))
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(data)
            current=os.fstat(stream.fileno())
            if (current.st_uid,current.st_gid)!=(st.st_uid,st.st_gid):
                os.fchown(stream.fileno(),st.st_uid,st.st_gid)
            os.fchmod(stream.fileno(),stat.S_IMODE(st.st_mode))
        os.replace(temporary,str(path))
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def legacy_trust_edits(base, bundle):
    """Migrate only exact paths emitted by this script's previous trust-copy mode."""
    legacy=str(base/'etc/cse-trust/ca-bundle.pem')
    edits=[]
    condarc=base/'.condarc'
    if condarc.exists():
        text=condarc.read_text()
        def replace(match):
            value=match.group(2).split('#',1)[0].strip().strip('\"\'')
            return match.group(1)+json.dumps(str(bundle)) if value==legacy else match.group(0)
        updated=re.sub(r'(?m)^(ssl_verify[ \t]*:[ \t]*)([^\n]*)$',replace,text)
        if updated!=text: edits.append((condarc,updated.encode()))
    state=base/'conda-meta/state'
    if state.exists():
        text=state.read_text();data=json.loads(text)
        variables=data.get('env_vars',{});changed=False
        for key in ('CONDA_SSL_VERIFY','REQUESTS_CA_BUNDLE','SSL_CERT_FILE','CURL_CA_BUNDLE','PIP_CERT'):
            if variables.get(key)==legacy: variables[key]=str(bundle);changed=True
        if variables.get('SSL_CERT_DIR')==str(base/'etc/cse-trust/empty-ca-dir'):
            del variables['SSL_CERT_DIR'];changed=True
        if changed: edits.append((state,(json.dumps(data,indent=2)+'\n').encode()))
    for path,data in edits:
        if base not in path.resolve(strict=True).parents or path.is_symlink():
            raise RuntimeError('Refusing linked/outside-prefix configuration edit: '+str(path))
    return edits


def maintain_native_trust(base, args):
    """Local PEM maintenance only; intentionally bypass every package-update step."""
    logdir=(args.log_dir or Path.home()/'.cse-trust-logs'/datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')).expanduser().resolve()
    if logdir==base or base in logdir.parents: raise RuntimeError('Logs must be outside the base installation')
    logdir.mkdir(mode=0o700,parents=True,exist_ok=False);os.chmod(str(logdir),0o700)
    with open(str(logdir/'run.log'),'w') as log:
        def say(message): print(message,flush=True);log.write(message+'\n');log.flush()
        say('Mode: '+('APPLY' if args.apply else 'LOCAL PREVIEW; no network operations'))
        say('Scope: existing native Miniforge PEM files | base: '+str(base))
        say('No package updates or environment permission normalization.')
        lock=None
        try:
            if args.apply:
                lock=open(str(base/'.cse-certificate-maintenance.lock'),'a')
                fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            paths=native_bundle_paths(base)
            extras=([args.ca_bundle] if args.ca_bundle else [])+args.extra_ca
            staged=[];details=[]
            for path in paths:
                before=path.read_bytes()
                text,removed=filtered_bundle([path]+extras)
                after=text.encode() if removed or extras else before
                changed=after!=before
                details.append({'path':str(path),'changed':changed,'roots_removed':removed,
                                'sha256':hashlib.sha256(after).hexdigest()})
                if changed: staged.append((path,after))
                say(('Would filter: ' if changed and not args.apply else 'Filter: ' if changed else 'Already clean: ')+str(path))
            edits=legacy_trust_edits(base,paths[0])
            for path,data in staged+edits:
                st=path.stat()
                if st.st_uid!=os.geteuid() or st.st_mode & (stat.S_ISUID|stat.S_ISGID):
                    raise RuntimeError('Owner review required before preserving file metadata: '+str(path))
                if hasattr(os,'listxattr') and any('acl' in key.lower() for key in os.listxattr(str(path))):
                    raise RuntimeError('Extended ACL needs owner/admin review: '+str(path))
            # Validate all contents before changing any file. Private backups include
            # metadata; replacements never modify a shared package-cache inode.
            if args.apply:
                for index,(path,data) in enumerate(staged+edits):
                    backup=logdir/('%03d-before-'%index+path.name)
                    backup.write_bytes(path.read_bytes())
                    st=path.stat()
                    (logdir/('%03d-file.json'%index)).write_text(json.dumps({'path':str(path),'backup':str(backup),'uid':st.st_uid,'gid':st.st_gid,'mode':stat.S_IMODE(st.st_mode)},indent=2))
                    replace_preserving_metadata(path,data)
                for path in paths:
                    if set(dict(pem_entries(path.read_text()))) & set(ROOTS):
                        raise RuntimeError('Known incident roots remain in '+str(path))
            status={'status':('written' if staged or edits else 'unchanged') if args.apply else 'planned',
                    'bundle':str(paths[0]),'mode':'native-pem','bundles':details,
                    'configuration_migrations':[str(p) for p,d in edits],
                    'sha256':hashlib.sha256(paths[0].read_bytes()).hexdigest() if args.apply else None}
            (logdir/'certificate-status.json').write_text(json.dumps(status,indent=2))
            (logdir/'summary.json').write_text(json.dumps([{'prefix':str(base),'status':'updated' if args.apply else 'previewed','issues':[],'changes_started':bool(args.apply and (staged or edits)),'package_changes':[],'trust_configuration':'existing native PEM files','certificate_status':status}],indent=2))
            say('Native certificate stage: '+status['status'].upper())
            if edits: say('Previous script-created CSE-path settings '+('redirected' if args.apply else 'would be redirected')+' to the existing native PEM.')
            legacy=str(base/'etc/cse-trust')+'/'
            stale=[key for key in ('CONDA_SSL_VERIFY','REQUESTS_CA_BUNDLE','SSL_CERT_FILE','CURL_CA_BUNDLE','PIP_CERT','SSL_CERT_DIR') if os.environ.get(key,'').startswith(legacy)]
            if stale: say('Current shell still has previous CSE-path exports: '+', '.join(stale)+'. Clear those old exports or start a fresh shell; a child process cannot change them.')
            say('No use-ca.sh or modulefile change is required for clients using the native bundles.')
            say('External custom trust settings and other environments are unchanged.')
            say('Private logs: '+str(logdir))
            return 0
        finally:
            if lock: lock.close()


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


def spec_name(spec):
    value=str(spec).rsplit('::',1)[-1]
    match=re.match(r'^([A-Za-z0-9_][A-Za-z0-9_.-]*)',value)
    if not match:raise RuntimeError('Cannot identify package in metadata/history spec: '+str(spec))
    return match.group(1)


def history_roots(prefix, meta):
    """Keep explicit user requests, excluding full installer/maintenance snapshots."""
    path=prefix/'conda-meta/history'
    if not path.is_file():return set()
    roots=set();state=set()
    for block in re.split(r'^==>.*<==\s*$',path.read_text(),flags=re.MULTILINE):
        for line in block.splitlines():
            if line.startswith(('+','-')):
                name=line[1:].rsplit('::',1)[-1].rsplit('-',2)[0]
                if line[0]=='+':state.add(name)
                else:state.discard(name)
        for line in block.splitlines():
            match=re.match(r'^# (update|install|create|remove) specs: (.*)$',line)
            if not match:continue
            try:
                values=ast.literal_eval(match.group(2))
                if not isinstance(values,(list,tuple)) or not all(isinstance(v,str) for v in values):raise ValueError('expected a spec list')
                names={spec_name(v) for v in values}
            except (ValueError,SyntaxError) as exc:
                raise RuntimeError('Cannot read package intent from '+str(path)+': '+str(exc)) from exc
            if match.group(1)=='remove':roots-=names
            elif names!=state:roots|=names
    return roots & set(meta)


def base_package_intent(meta, prefix=None, config=None, ignore_pins=False, held=()):
    """Preserve explicit requests and every source component of the dependency graph.

    Keeping source components covers every installed package initially, including
    isolated packages and cycles. New dependencies are then chosen by the solver.
    Full explicit installer/maintenance snapshots are not application intent.
    """
    names=set(meta)
    graph={n:{spec_name(d) for d in r.get('depends',())} & names for n,r in meta.items()}
    reverse={n:set() for n in graph}
    for n,deps in graph.items():
        for dep in deps:reverse[dep].add(n)
    visited=set();order=[]
    for start in sorted(graph):
        stack=[(start,False)]
        while stack:
            n,done=stack.pop()
            if done:order.append(n);continue
            if n in visited:continue
            visited.add(n);stack.append((n,True))
            stack.extend((dep,False) for dep in sorted(graph[n]) if dep not in visited)
    components=[];component={}
    for start in reversed(order):
        if start in component:continue
        members=set();stack=[start]
        while stack:
            n=stack.pop()
            if n in component:continue
            component[n]=len(components);members.add(n);stack.extend(reverse[n])
        components.append(members)
    sources=set(range(len(components)))
    for n,deps in graph.items():
        sources-={component[d] for d in deps if component[n]!=component[d]}
    roots=set().union(*(components[i] for i in sources)) if sources else set()
    explicit=history_roots(prefix,meta) if prefix is not None else set()
    pins=list((config or {}).get('pinned_packages') or [])
    pinfile=prefix/'conda-meta/pinned' if prefix is not None else None
    if pinfile is not None and pinfile.is_file():
        pins.extend(line.split('#',1)[0].strip() for line in pinfile.read_text().splitlines() if line.split('#',1)[0].strip())
    pinned=({spec_name(pin) for pin in pins} & names) if not ignore_pins else set()
    roots|=explicit | (set(meta) & (set(MINIMUM)|{'conda','python','mamba','conda-libmamba-solver'}))
    roots|=pinned | set(held)
    # Verified conda-forge naming migration: current recipes prohibit the old
    # boost/boost-cpp names. Preserve headers/development functionality too.
    # https://github.com/conda-forge/boost-feedstock/blob/main/recipe/meta.yaml
    forge=set(requested_channels([],{k:v for k,v in (config or {}).items() if k!='pinned_packages'})[1])
    forge.update(('conda-forge','https://conda.anaconda.org/conda-forge'))
    migrations=[]
    for old,new in sorted(BASE_REPLACEMENTS.items()):
        if old in meta and old not in pinned and old not in held and recorded_origin(meta[old]) in forge:
            roots.discard(old);roots.update(new)
            migrations.append({'name':old,'replacements':list(new),'reason':'conda-forge Boost package naming migration'})
    return {'roots':sorted(roots),'explicit_requests':sorted(explicit),'pinned_packages':sorted(pinned),
            'ignored_pins':sorted(set(pins)) if ignore_pins else [],
            'dependencies':sorted(set(meta)-roots-{r['name'] for r in migrations}),
            'replacements':migrations}


def package_paths(record):
    """Read installed prefix manifests, rejecting paths outside the prefix."""
    files=record.get('files') or ()
    data=record.get('paths_data') or {}
    if not isinstance(files,(list,tuple)) or not all(isinstance(p,str) for p in files) or not isinstance(data,dict):
        raise RuntimeError('Malformed installed package file manifest')
    paths=data.get('paths') or ()
    if not isinstance(paths,(list,tuple)) or not all(isinstance(p,dict) for p in paths):raise RuntimeError('Malformed installed package path records')
    values=set(files)
    values.update(p['_path'] for p in paths if p.get('_path'))
    for value in sorted(values):
        p=Path(value)
        if not value or p.is_absolute() or '..' in p.parts or '\\' in value:
            raise RuntimeError('Unsafe installed package path: '+str(value))
        yield p


def first_blocked_parent(prefix, path):
    """Name the first untraversable ancestor whose owner may repair access."""
    parents=list(reversed(Path(path).parents))
    for parent in parents:
        if not os.access(str(parent),os.X_OK):
            # Missing directories are prospective creation paths, not hidden trees.
            try:parent.lstat()
            except FileNotFoundError:continue
            except OSError:return parent
            return parent
    return None


def hold_paths(holds):
    for hold in holds.values():
        yield from hold.get('blocked_paths') or [{'path':hold['path'],'reason':hold['reason'],
                                                 'blocking_path':str(Path(hold['path']).parent)}]


def permission_holds(prefix, meta, issues=None, include_directories=False):
    """Find package replacement blockers without writing, chmod or deletion.

    A foreign file owner is not itself a blocker: Unix rename/unlink depends on
    its parent. Cache directory access checks are shared across package files.
    This preflight cannot establish immutable flags, server policy or future ACLs.
    """
    holds={};directory_checks={}
    python_record=meta.get('python',{})
    python=str(python_record.get('version','') if isinstance(python_record,dict) else '').split('.')
    tag=''.join(python[:2]) if len(python)>=2 else None
    def directory_check(directory):
        if directory in directory_checks:return directory_checks[directory]
        if directory==prefix.parent:
            result=(None,'Directory is outside the selected prefix',directory)
        else:
            try:
                st=directory.lstat()
                if stat.S_ISLNK(st.st_mode):result=(None,'Package parent is a symlink; access needs review',directory)
                elif not stat.S_ISDIR(st.st_mode):result=(None,'Package parent is not a directory',directory)
                elif not os.access(str(directory),os.W_OK|os.X_OK):
                    target=first_blocked_parent(prefix,directory/'entry') or directory
                    result=(None,'Containing directory lacks effective write/traverse access',target)
                else:
                    # Check ancestors for redirected paths, too; os.access has
                    # already checked effective traversal through them.
                    redirect=next((p for p in directory.parents if p!=prefix and prefix in p.parents and p.is_symlink()),None)
                    result=(st,None,None) if redirect is None else (None,'Package parent traverses a symlink: '+str(redirect),redirect)
            except FileNotFoundError:result=directory_check(directory.parent)
            except OSError as exc:result=(None,str(exc),first_blocked_parent(prefix,directory/'entry') or directory)
        directory_checks[directory]=result
        return result
    for name,record in sorted(meta.items()):
        try:paths=list(package_paths(record))
        except (TypeError,ValueError,RuntimeError,KeyError,AttributeError) as exc:
            if issues is None:raise
            issues.append({'path':str(prefix/'conda-meta'),'package':name,'reason':'Cannot inspect package manifest: '+str(exc)})
            continue
        directory_entries={Path(p['_path']) for p in ((record.get('paths_data') or {}).get('paths') or ())
                           if p.get('_path') and p.get('path_type')=='directory'}
        candidates=list(paths);seen=set(paths)
        # Native packages can leave import-generated caches out of their manifest.
        # Associate only caches derived from a package-owned .py source, never
        # infer package ownership just from the word android_deploy in a name.
        for p in paths:
            if p.suffix=='.py' and tag:
                for suffix in ('','.opt-1','.opt-2'):
                    cache=p.parent/'__pycache__'/(p.stem+'.cpython-'+tag+suffix+'.pyc')
                    if cache not in seen:candidates.append(cache);seen.add(cache)
        for relative in candidates:
            path=prefix/relative
            reason=None;st=None;exists=None
            try:
                st=path.lstat();exists=True
                if stat.S_ISDIR(st.st_mode) and (not include_directories or relative in directory_entries):continue
            except FileNotFoundError:st=None;exists=False
            except OSError as exc:
                reason=str(exc)
            parent,blocked,blocking_path=directory_check(path.parent)
            reason=reason or blocked
            if not reason and st is not None and parent.st_mode & stat.S_ISVTX and os.geteuid() not in (0,st.st_uid,parent.st_uid):
                reason='Sticky containing directory prevents replacing another owner\'s file'
                blocking_path=path.parent
            if reason:
                if name not in holds:
                    holds[name]={'name':name,'version':record['version'],'build':record['build'],
                                 'path':str(path),'reason':reason,'access':access_snapshot(path),
                                 'python_files':any(p.suffix in ('.py','.pyc') for p in paths) or record.get('noarch')=='python',
                                 'blocked_paths':[]}
                holds[name]['blocked_paths'].append({'path':str(path),'reason':reason,
                    'blocking_path':str(blocking_path or first_blocked_parent(prefix,path) or path.parent),
                    'exists':exists,'file_uid':st.st_uid if st is not None else None,
                    'file_gid':st.st_gid if st is not None else None})
    return holds


def permission_hold_specs(meta, specs, holds, conda_minimum=CONDA_MINIMUM):
    """Temporary constraints for this solve, independent of stored site pins."""
    for name,hold in holds.items():
        minimum=MINIMUM.get(name,conda_minimum if name=='conda' else None)
        if minimum and version(hold['version'])<version(minimum):
            raise RuntimeError('Permission-held package %s=%s cannot meet required >=%s; owner/admin must repair %s (%s)'%(
                name,hold['version'],minimum,hold['path'],hold['reason']))
    output=[s for s in specs if spec_name(s) not in holds]
    output.extend(n+'='+r['version']+'='+r['build'] for n,r in sorted(holds.items()))
    constraint=None
    if 'python' in meta and 'python' not in holds and any(r['python_files'] for r in holds.values()):
        constraint='python='+'.'.join(meta['python']['version'].split('.')[:2])+'.*'
        output=[s for s in output if spec_name(s)!='python']+[constraint]
    return output,constraint


def verify_permission_holds(plan, holds):
    touched={r['name'] for action in ('LINK','UNLINK') for r in plan.get('actions',{}).get(action,())} & set(holds)
    if touched:raise RuntimeError('Plan would replace permission-held packages: '+', '.join(sorted(touched))+'; no transaction attempted. Repair their reported access blockers.')


def plan_specs(meta, upgrade_conda, broad=False, conda_minimum=CONDA_MINIMUM, roots=None):
    if broad:
        targets=set(base_package_intent(meta)['roots'] if roots is None else roots)|{'curl'}
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


def check_plan(plan, allowed, retained=None):
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
    removed=unlinked-linked
    if removed and (retained is None or removed & set(retained)):
        raise RuntimeError('Rejected package removal without replacement: ' + ', '.join(sorted(removed if retained is None else removed & set(retained))))
    return sorted(linked | unlinked)


def exact_plan_specs(meta, plan, origins, extras, config):
    """Bind the validated final package versions/builds and allowed sources."""
    final={n:(r['version'],r['build']) for n,r in meta.items()}
    final_origins=dict(origins)
    for record in plan.get('actions',{}).get('UNLINK',[]):
        final.pop(record['name'],None)
        final_origins.pop(record['name'],None)
    for record in plan.get('actions',{}).get('LINK',[]):
        name=record['name']
        final[name]=(record['version'],record.get('build_string') or record.get('build'))
        # LINK JSON can use a bare canonical label for a file/site channel while
        # base_url carries its actual location. Do not turn that label into an
        # unrelated conda.anaconda.org repository during the execution solve.
        source_record=dict(record,channel=record['base_url']) if record.get('base_url') else record
        _,_,_,planned_origins,_,_=environment_channels({name:source_record},extras,config)
        if name in planned_origins:final_origins[name]=planned_origins[name]
    if any(not build for value,build in final.values()):
        raise RuntimeError('Plan omitted build identifiers')
    exact=qualify_specs([name+'='+value+'='+build for name,(value,build) in sorted(final.items())],final_origins)
    return final,exact


def verify_retained(final, retained):
    missing=set(retained)-set(final)
    if missing:raise RuntimeError('Required base applications missing from plan: '+', '.join(sorted(missing)))


def verify_installed_plan(final, installed):
    actual={n:(r['version'],r['build']) for n,r in installed.items()}
    differences={n for n in set(final)|set(actual) if final.get(n)!=actual.get(n)}
    if differences:raise RuntimeError('Installed packages differ from validated plan: '+', '.join(sorted(differences)))


def planned_removals(plan, migrations):
    linked={r['name'] for r in plan.get('actions',{}).get('LINK',[])}
    replacements={r['name']:r['replacements'] for r in migrations}
    return [{'name':r['name'],'before':r['version'],'status':'planned',
             'reason':'superseded by '+', '.join(replacements[r['name']]) if r['name'] in replacements else
                      'not needed by the updated retained package set'}
            for r in plan.get('actions',{}).get('UNLINK',[]) if r['name'] not in linked]


XKB_PATH = 'share/X11/xkb'
XKB_LINK = '../xkeyboard-config-2'
# Keep the backup beside xkb so Conda's empty-parent cleanup cannot remove X11
# during rollback; the move also stays on the source filesystem.
PATH_BACKUPS = 'share/X11/.cse-trust-path-backups'
XKB_CACHE_PROBE = r'''
import json, os, sys
from pathlib import Path
from conda.plugins.manager import CondaPluginManager
CondaPluginManager.load_entrypoints = lambda self, *args, **kwargs: 0
from conda.base.context import context
record=json.loads(sys.argv[1])
build=record.get('build_string') or record.get('build')
parts=[record['name'],record['version'],build]
if any(not v or '/' in v or '\\' in v or v in ('.','..') for v in parts):
    raise RuntimeError('Invalid planned package identifier')
for cache in context.pkgs_dirs:
    root=Path(cache)/'-'.join(parts)
    info=root/'info/paths.json'
    if not info.is_file():continue
    index=json.loads((root/'info/index.json').read_text())
    if any(str(index.get(k))!=str(v) for k,v in zip(('name','version','build'),parts)):continue
    paths=json.loads(info.read_text())['paths']
    entry=next((r for r in paths if r['_path']=='share/X11/xkb'),None)
    if entry and entry['path_type']=='softlink':
        link=root/'share/X11/xkb'
        if not link.is_symlink():raise RuntimeError('Cached XKB symlink is not a symlink: '+str(link))
        print(json.dumps({'available':True,'target':os.readlink(link),'package_dir':str(root)}))
    else:print(json.dumps({'available':True,'target':None,'package_dir':str(root)}))
    break
else:print(json.dumps({'available':False}))
'''


def no_link_parents(prefix, path):
    for parent in reversed(path.parent.parents):
        if parent==prefix or prefix in parent.parents:
            if parent.is_symlink():raise RuntimeError('Refusing XKB migration through symlink parent: '+str(parent))
    if path.parent.is_symlink():raise RuntimeError('Refusing XKB migration through symlink parent: '+str(path.parent))


def inspect_xkb_tree(prefix, meta):
    source=prefix/XKB_PATH
    no_link_parents(prefix,source)
    target=prefix/'share/xkeyboard-config-2'
    if target.is_symlink() or (target.exists() and not target.is_dir()):
        raise RuntimeError('XKB replacement data path must be a real directory or absent: '+str(target))
    st=source.lstat()
    if not stat.S_ISDIR(st.st_mode):raise RuntimeError('XKB migration requires a real directory: '+str(source))
    declared=lambda r:set(r.get('files',[]))|{p['_path'] for p in r.get('paths_data',{}).get('paths',[])}
    owned=declared(meta.get('xkeyboard-config',{}))
    other={p for name,r in meta.items() if name!='xkeyboard-config' for p in declared(r) if p.startswith(XKB_PATH+'/')}
    seen=[];untracked=[];stack=[source]
    while stack:
        with os.scandir(stack.pop()) as entries:
            for entry in entries:
                mode=entry.stat(follow_symlinks=False).st_mode
                path=Path(entry.path);relative=path.relative_to(prefix).as_posix()
                if stat.S_ISDIR(mode):stack.append(path)
                elif stat.S_ISREG(mode) or stat.S_ISLNK(mode):
                    seen.append(relative)
                    if relative not in owned or relative in other:untracked.append(relative)
                else:raise RuntimeError('Special file blocks XKB migration: '+str(path))
    if untracked:raise RuntimeError('XKB directory contains untracked or other-package files; left untouched: '+', '.join(sorted(untracked)[:20]))
    return {'source':str(source),'files':sorted(seen),'device':st.st_dev,'inode':st.st_ino,
            'uid':st.st_uid,'gid':st.st_gid,'mode':stat.S_IMODE(st.st_mode)}


def save_xkb_manifest(migration):
    path=Path(migration['manifest'])
    fd,tmp=tempfile.mkstemp(prefix='.manifest-',dir=str(path.parent))
    try:
        with os.fdopen(fd,'w') as stream:
            json.dump(migration,stream,indent=2);stream.flush();os.fsync(stream.fileno())
        os.replace(tmp,str(path))
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


def preserve_xkb_tree(prefix, meta, migration):
    inspection=inspect_xkb_tree(prefix,meta)
    if not os.access(str((prefix/XKB_PATH).parent),os.W_OK|os.X_OK):
        raise RuntimeError('XKB parent directory is not writable/traversable: '+str((prefix/XKB_PATH).parent))
    root=prefix/PATH_BACKUPS
    no_link_parents(prefix,root/'run')
    marker=root/'managed-by-patch-miniforge-trust'
    if root.exists() and not marker.is_file():raise RuntimeError('Refusing an unmanaged XKB backup directory: '+str(root))
    root.mkdir(mode=0o2775,exist_ok=True)
    if root.is_symlink():raise RuntimeError('XKB backup directory is a symlink: '+str(root))
    if root.stat().st_uid==os.geteuid():
        os.chown(str(root),-1,maintenance_gid());os.chmod(str(root),0o2775)
    if not marker.exists():marker.write_text('CSE XKB path migration backups v1\n')
    directory=Path(tempfile.mkdtemp(prefix='xkb-',dir=str(root)))
    migration.update(inspection,status='prepared',backup=str(directory/'xkb'),manifest=str(directory/'manifest.json'))
    save_xkb_manifest(migration)  # Record the recovery paths before moving data.
    source=Path(inspection['source']);st=source.lstat()
    if (st.st_dev,st.st_ino)!=(inspection['device'],inspection['inode']):
        raise RuntimeError('XKB directory changed during migration preflight')
    os.rename(str(source),migration['backup'])  # Same-prefix move; no copy/delete fallback.
    migration['status']='preserved';save_xkb_manifest(migration)


def restore_xkb_tree(prefix, before, migration):
    if migration.get('status')!='preserved':return
    identity=lambda meta:{n:(r['version'],r['build']) for n,r in meta.items()}
    if identity(records(prefix))!=identity(before):
        migration.update(status='recovery-needed',reason='Conda package records did not roll back; original tree retained in backup')
        save_xkb_manifest(migration);return
    backup=Path(migration['backup']);no_link_parents(prefix,backup);st=backup.lstat()
    if not stat.S_ISDIR(st.st_mode) or (st.st_dev,st.st_ino)!=(migration['device'],migration['inode']):
        raise RuntimeError('Original XKB backup identity changed; manual recovery required')
    source=Path(migration['source']);no_link_parents(prefix,source)
    if source.is_symlink() and os.readlink(str(source))==XKB_LINK:source.unlink()
    elif source.exists():source.rmdir()  # Only an empty real directory may be replaced.
    os.rename(migration['backup'],str(source))
    migration['status']='restored-after-failure';save_xkb_manifest(migration)


def verify_xkb_tree(prefix, migration):
    source=prefix/XKB_PATH;no_link_parents(prefix,source)
    if (prefix/'share/xkeyboard-config-2').is_symlink() or not source.is_symlink() or os.readlink(str(source))!=XKB_LINK or not (source/'geometry/hp').is_file():
        raise RuntimeError('Installed XKB directory-to-symlink migration is incomplete: '+str(source))
    migration['status']='installed-original-preserved';save_xkb_manifest(migration)


def conda_update_status(meta):
    current=meta.get('conda',{}).get('version')
    return {'status':'not-installed' if current is None else
            ('would-update' if version(current)<version(CONDA_MINIMUM) else 'would-check-newest'),
            'before':current,'minimum':CONDA_MINIMUM,
            'policy':'Conda and base packages update together in one transaction'}


def select_conda_target(base, meta, origins, config, offline, runjson, logdir, row, say, candidate_prefix=None):
    status=row['conda_update']
    if status['before'] is None:return CONDA_MINIMUM
    source=origins.get('conda') or requested_channels([],{k:v for k,v in config.items() if k!='pinned_packages'})[1][0]
    row['phase']='find newest stable base conda'
    search=[base/'bin/conda','search','--json','--override-channels','--channel',source,
            '--repodata-fn','current_repodata.json','conda']
    if offline:search.append('--offline')
    available=runjson(search)
    (logdir/'base-conda-search.json').write_text(json.dumps(available,indent=2))
    stable=[r['version'] for r in available.get('conda',[])
            if re.fullmatch(r'\d+(?:\.\d+)*',str(r.get('version','')))]
    if not stable:raise RuntimeError('No stable Conda release available from '+source)
    latest=max(stable,key=version)
    if version(latest)<version(CONDA_MINIMUM):
        raise RuntimeError('Newest available Conda is %s from %s; required >=%s%s'%(
            latest,source,CONDA_MINIMUM,' (offline metadata may be stale)' if offline else ''))
    target=max((latest,status['before']),key=version)
    status.update(status='planned',latest_available=latest,source=source,target=target)
    if candidate_prefix:
        status['policy']='Fresh private candidate; source manager remains unchanged'
        say('Candidate Conda target: source=%s; newest stable=%s; target>=%s; private prefix=%s'%(
            status['before'],latest,target,candidate_prefix))
    else:
        say('Base Conda update: installed=%s; newest stable=%s; target>=%s; same prefix, one base transaction'%(
            status['before'],latest,target))
    return target


LIBMAMBA_CLI = r'''
import json, os, sys
# Prevent all entry-point discovery before Conda constructs its plugin manager.
from conda.plugins.manager import CondaPluginManager
CondaPluginManager.load_entrypoints = lambda self, *args, **kwargs: 0
# The registry contains built-ins plus the one solver hook registered below.
# no_plugins must be false so CLI initialization retains that explicit hook.
os.environ['CONDA_NO_PLUGINS'] = 'false'
from conda import plugins
from conda.plugins.types import CondaSolver
from conda.base.context import context
from conda.cli.main import main
from conda.models.channel import Channel
from conda.models import match_spec as match_spec_module
# Legacy MatchSpec parsing drops a file channel's directory and leaves only its
# basename, which the next parse mistakes for an anaconda.org channel. Preserve
# the actual approved file URL through the CLI/solver roundtrip, in this process.
parse_channel = getattr(match_spec_module, '_parse_channel', None)
if parse_channel is not None:
    def parse_local_channel(value):
        if value and value.startswith('file://'):
            channel=Channel(value)
            return channel.base_url,channel.subdir
        return parse_channel(value)
    match_spec_module._parse_channel=parse_local_channel
channel_match_str=match_spec_module.ChannelMatch.__str__
def local_channel_str(self):
    channel=getattr(self, '_raw_value', None)
    if getattr(channel, 'scheme', None)=='file':return channel.base_url
    return channel_match_str(self)
match_spec_module.ChannelMatch.__str__=local_channel_str
from conda_libmamba_solver.solver import LibMambaSolver
import conda_libmamba_solver.solver as solver_module
approved_path=os.environ.get('CSE_CONDA_APPROVED_PLAN')
if approved_path:
    with open(approved_path) as stream:approved=json.load(stream)
else:approved={}
def retired_names(state):
    replacements=__CSE_BASE_REPLACEMENTS__
    retired={old for old,new in replacements.items() if state.prune and old in state.installed and
             old not in state.requested and all(n in state.requested for n in new)}
    if state.prune and approved and os.path.realpath(str(state.prefix))==approved['prefix']:
        retired.update(set(state.installed)-set(approved['packages']))
    return retired
# Conda 24.11's install CLI parses --prune but omits it from the solver call.
# Honor the explicit flag through the public transaction API in this process.
class RetainedBaseSolver(LibMambaSolver):
    def solve_for_transaction(self, *args, **kwargs):
        if '--prune' in sys.argv:
            if len(args)>2:args=(*args[:2],True,*args[3:])
            else:kwargs['prune']=True
        transaction=super().solve_for_transaction(*args, **kwargs)
        # Recheck the execution solve before any unlink/link action. Even a
        # same-build reinstall or Python-triggered noarch relink is forbidden.
        guard=json.loads(os.environ.get('CSE_CONDA_PERMISSION_HOLDS','{}'))
        for setup in transaction.prefix_setups.values():
            if os.path.realpath(setup.target_prefix)==guard.get('prefix'):
                touched={r.name for r in (*setup.unlink_precs,*setup.link_precs)} & set(guard['packages'])
                if touched:
                    from conda.exceptions import CondaError
                    raise CondaError('Transaction would replace permission-held packages: '+', '.join(sorted(touched))+'; no transaction attempted')
            if approved and os.path.realpath(setup.target_prefix)==approved['prefix']:
                from conda.core.prefix_data import PrefixData
                from conda.exceptions import CondaError
                installed={r.name:r for r in PrefixData(setup.target_prefix).iter_records()}
                before={n:[r.version,r.build] for n,r in installed.items()}
                if before!=approved['before']:
                    raise CondaError('Base package inventory changed since promotion preflight; no transaction attempted')
                for record in setup.unlink_precs:installed.pop(record.name,None)
                installed.update({r.name:r for r in setup.link_precs})
                differences=set(installed)^set(approved['packages'])
                for name in set(installed)&set(approved['packages']):
                    record=installed[name];expected=approved['packages'][name]
                    if (record.version,record.build,record.subdir)!=(expected['version'],expected['build'],expected['subdir']):
                        differences.add(name);continue
                    common=[key for key in ('sha256','md5') if expected.get(key) and getattr(record,key,None)]
                    if not common or any(expected[key]!=getattr(record,key) for key in common):differences.add(name)
                if differences:
                    raise CondaError('Solver result differs from reviewed package versions/builds/checksums: '+', '.join(sorted(differences))+'; no transaction attempted')
        return transaction
    # Explicitly retire the old names during the solve, so they cannot bias it
    # toward older replacement versions before post-solve dependency pruning.
    def _specs_to_tasks_add(self, in_state, out_state):
        tasks=super()._specs_to_tasks_add(in_state, out_state)
        import libmambapy as api
        tasks.setdefault(('ERASE',api.SOLVER_ERASE),[]).extend(sorted(retired_names(in_state)))
        return tasks
    def _specs_to_request_jobs_add(self, in_state, out_state):
        tasks=super()._specs_to_request_jobs_add(in_state, out_state)
        from libmambapy.solver import Request
        tasks.setdefault(Request.Remove,[]).extend(sorted(retired_names(in_state)))
        return tasks
# --update-all otherwise creates update jobs for retired names before pruning.
# They are neither requests nor dependencies of the new replacement packages.
class RetainedBaseInputState(solver_module.SolverInputState):
    @property
    def always_update(self):
        updates=super().always_update
        if not self.prune:return updates
        retired=retired_names(self)
        return {n:spec for n,spec in updates.items() if n not in retired}
solver_module.SolverInputState=RetainedBaseInputState
class SolverOnly:
    @plugins.hookimpl
    def conda_solvers(self):
        yield CondaSolver(name='libmamba', backend=RetainedBaseSolver)
manager = context.plugin_manager
manager.disable_external_plugins()
manager.register(SolverOnly(), name='cse-libmamba-solver-only')
manager.get_cached_solver_backend.cache_clear()
if sys.argv[1:] == ['__cse_solver_probe__']:
    from conda import __version__
    external = [name for name, plugin in manager.list_name_plugin()
                if plugin is not None and not name.startswith('conda.plugins.')]
    if external != ['cse-libmamba-solver-only']:
        raise RuntimeError('Unexpected external plugins: '+repr(external))
    manager.get_solver_backend('libmamba')
    print(json.dumps({'success':True,'solver':'libmamba','conda_version':__version__,
                      'external_plugins':external}))
else:
    sys.exit(main(*sys.argv[1:]))
'''.replace('__CSE_BASE_REPLACEMENTS__',repr(BASE_REPLACEMENTS))


def solver_invocation(base, cmd):
    values=list(map(str,cmd))
    if values and values[0]==str(base/'bin/conda'):
        probe=values[1:]==['__cse_solver_probe__']
        solve=len(values)>1 and values[1]=='install' and '--solver' in values and values[values.index('--solver')+1]=='libmamba'
        if probe or solve:return [str(base/'bin/python'),'-I','-B','-c',LIBMAMBA_CLI]+values[1:]
    return values


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
        if row.get('package_pin_policy'):say('  Package pins: '+row['package_pin_policy'])
        if row.get('ignored_pins'):say('  Ignored base pin specs: '+', '.join(row['ignored_pins']))
        if row.get('promotion'):
            p=row['promotion'];say('  Reviewed promotion: %s | %d packages | SHA256=%s | stage=%s'%(
                p['status'],p['package_count'],p['manifest_sha256'],p['stage']))
        if row.get('permission_preflight'):
            a=row['permission_preflight'];say('  Permission preflight: %d affected paths; %d repair targets; %d inspection gaps | %s'%(
                a['affected_path_count'],a['repair_target_count'],a['inspection_gap_count'],a['report_directory']))
        if row.get('reviewed_security_versions'):
            say('  Reviewed security versions (candidate): '+', '.join('%s=%s'%(n,v['version']) for n,v in sorted(row['reviewed_security_versions'].items())))
        for hold in row.get('permission_holds',[]):
            say('  Deferred package: %s=%s=%s | %s | %s'%(hold['name'],hold['version'],hold['build'],hold['path'],hold['reason']))
        if row.get('permission_python_constraint'):say('  Python constraint for deferred packages: '+row['permission_python_constraint'])
        if row.get('xkb_migration'):
            migration=row['xkb_migration']
            say('  XKB path migration: '+migration.get('status','not moved')+' | original tree: '+migration.get('backup','not moved')+' | manifest: '+migration.get('manifest','not created'))
            if migration.get('reason'):say('  XKB recovery note: '+migration['reason'])
        for target in row.get('package_targets',[]):
            say('  Package target: %s %s -> %s | source=%s' % (target['name'],target['current'],target['request'],target.get('source','not recorded')))
        for change in row.get('package_plan',[]):
            say('  Solver plan: %s %s -> %s (build %s)' % (change['name'],change['before'],change['after'],change['build']))
        for change in row.get('package_changes',[]):
            say('  Verified package: %s %s -> %s' % (change['name'],change['before'],change['after']))
        for removal in row.get('package_removals',[]):
            say('  %s removal: %s=%s | %s'%(removal.get('status','planned').capitalize(),removal['name'],removal['before'],removal['reason']))
        if row.get('security_verification'):
            say('  Verified required minimums: '+', '.join('%s=%s (>= %s)'%(n,v['version'],v['minimum']) for n,v in sorted(row['security_verification'].items())))
        if row.get('conda_update') or row.get('conda_bootstrap'):
            bootstrap=row.get('conda_update') or row['conda_bootstrap']
            say('  Conda update: %s | before=%s | after=%s | minimum=%s'%(
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
        if row.get('package_change_list'):say('  User package change list: '+row['package_change_list']['path'])
        if row.get('permission_warnings'): say('  Permission/access skips: %d; see skip reports' % len(row['permission_warnings']))
        if row.get('phase') and row['status']=='incomplete': say('  Failed/review phase: '+row['phase'])
        for issue in row['issues']: say('  Reason: '+issue)
        for snapshot in row.get('access_details',[]): print_access(snapshot,say)
        for event in row.get('command_failures',[]):
            for snapshot in event.get('access_details',[]): print_access(snapshot,say)
    say('Environment counts: '+', '.join('%s=%d'%(s,sum(r['status']==s for r in results)) for s in ('previewed','previewed-with-skips','updated','updated-with-skips','skipped','incomplete')))
    say('Counts are environments, not package versions. Deferred packages remain installed at their listed versions. Incomplete means a required package/check failed or needs review; reasons appear above.')
    if not apply:
        if any(row.get('promotion') for row in results):say('Reviewed promotion performed a dependency dry run; no package/configuration/permission changes were applied to base.')
        else:say('Preview targets are requests, not solved upgrades. No dependency solve ran; exact versions/builds are validated during apply.')


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
        return 'Conda classic conflict-reporting bug', 'Conda classic crashed while explaining a dependency conflict. Use the current libmamba update path; it reports conflicts without classic hint analysis.'
    if 'non-conda' in value or 'conda-forge migration' in value:
        return 'Mixed package ownership', 'Review the named pip/uv-managed tool and its requirements; do not overwrite it with conda in bulk.'
    if any(x in value for x in ('permission denied','permissionerror','permission-held','not writable','notwritableerror','read-only file system')):
        if '__pycache__' in value or '.pyc' in value:
            return 'Filesystem access', 'The denied path is generated Python bytecode. Conda may need to rename/remove it during package replacement, even if the application is unused. Check the containing directory write/traverse access, sticky bit and ACLs; group membership does not grant chmod on another owner\'s file. Have the owner/admin repair the specific blocker. Deleting one cache file does not repair a non-writable directory. Permission-normalization skips alone are nonfatal.'
        return 'Filesystem access', 'Check the exact denied path, its parent traversal, ACLs, mount policy and cache location; environment ownership alone is insufficient.'
    if any(x in value for x in ('fileexistserror','clobbererror','file exists','directory-to-symlink','xkb migration')):
        return 'Package file collision', 'Check the named filesystem path and any saved XKB migration manifest. A longer dependency solve will not repair an existing-path collision. Existing package-owned XKB directories are preserved before the known symlink migration; custom/other-package contents require review.'
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
        candidates = [p for p in root.iterdir() if p.is_dir() and ((p/'summary.json').is_file() or (p/'permission-summary.json').is_file())]
        if not candidates: raise RuntimeError('No completed summary found under '+str(root))
        directory = max(candidates,key=lambda p:((p/'summary.json' if (p/'summary.json').is_file() else p/'permission-summary.json').stat().st_mtime_ns,p.name))
    return Path(directory).expanduser().resolve(strict=True)


def report_existing(directory, verbose=False):
    directory = report_directory(directory)
    if (directory/'verification-summary.json').is_file():return report_user_verification(directory)
    if (directory/'permission-summary.json').is_file() and not (directory/'summary.json').is_file():
        print('READ-ONLY PERMISSION REPORT: '+str(directory))
        print((directory/'permission-preflight/permissions.txt').read_text())
        print('Saved access evidence only; no updates, new scan or messages to owners were performed.')
        return 0
    if (directory/'stage-summary.json').is_file():return report_stage_existing(directory,verbose)
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
        if row.get('package_change_list'):print('User package change list: '+row['package_change_list']['path'])
        if row['status'] not in ('incomplete','skipped') and not row.get('permission_holds') and not row.get('promotion') and not verbose: continue
        issues = row.get('issues',[])
        evidence = row.get('command_failures',[])
        if not evidence and any('Command failed; see private run.log' in issue for issue in issues):
            inferred = legacy_failure_details(logtext,row['prefix'])
            if inferred: evidence = [inferred]
        cause_text = '\n'.join(issues+[e['detail'] for e in evidence])
        if row.get('promotion') and not issues:
            category,advice='Reviewed promotion', 'Saved promotion status: '+row['promotion']['status']+'. No new update or runtime check was performed by this report.'
        elif row.get('permission_holds') and not issues:
            category='Deferred packages'
            advice=('The validated update completed with the listed packages held at their installed versions.'
                    if row['status'].startswith('updated') else 'Local preview found the listed access-blocked packages; no update was performed.')
            advice+=' Repair their access before updating them.'
        else:
            category,advice = failure_category(cause_text)
            failures.append(category)
        print('\n%s | %s | owner=%s' % (row['prefix'],row['status'],row.get('ownership',{}).get('owner','unknown')))
        print('  Category: '+category)
        print('  Changes started: '+str(row.get('changes_started','not recorded'))+' (not a transaction/rollback guarantee)')
        if row.get('conda_update') or row.get('conda_bootstrap'):
            bootstrap=row.get('conda_update') or row['conda_bootstrap']
            print('  Conda update: %s | before=%s | after=%s'%(
                bootstrap['status'],bootstrap['before'],bootstrap.get('after','not changed/verified')))
            if bootstrap.get('latest_available'):
                print('  Newest stable Conda available: %s | source=%s'%(bootstrap['latest_available'],bootstrap['source']))
        for issue in issues:
            if 'Command failed; see private run.log' not in issue: print('  Reason: '+issue)
        if row.get('package_pin_policy'):print('  Package pins: '+row['package_pin_policy'])
        if row.get('ignored_pins'):print('  Ignored base pin specs: '+', '.join(row['ignored_pins']))
        if row.get('promotion'):
            p=row['promotion'];print('  Reviewed promotion: %s | %d packages | SHA256=%s | stage=%s'%(
                p['status'],p['package_count'],p['manifest_sha256'],p['stage']))
        for hold in row.get('permission_holds',[]):
            print('  Deferred package: %s=%s=%s | %s | %s'%(hold['name'],hold['version'],hold['build'],hold['path'],hold['reason']))
        if row.get('permission_python_constraint'):print('  Python constraint for deferred packages: '+row['permission_python_constraint'])
        if row.get('xkb_migration'):
            migration=row['xkb_migration']
            print('  XKB path migration: '+migration.get('status','not moved')+' | original tree: '+migration.get('backup','not moved')+' | manifest: '+migration.get('manifest','not created'))
            if migration.get('reason'):print('  XKB recovery note: '+migration['reason'])
        for removal in row.get('package_removals',[]):
            print('  %s removal: %s=%s | %s'%(removal.get('status','planned').capitalize(),removal['name'],removal['before'],removal['reason']))
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
    print('updated-with-skips means the validated update completed with access/permission exceptions, including any listed deferred packages left at their installed versions.')
    print('Legacy diagnostics are best-effort evidence from saved logs, not a new system test.')
    return 0


def diagnostic_argv(base, prefix, argv, requested):
    """Rebuild only our install command; saved logs are data, never shell code."""
    if len(argv)<2 or Path(argv[0]).resolve()!=(base/'bin/conda').resolve() or argv[1]!='install':
        raise RuntimeError('Saved failure is not an install from the currently selected base')
    switches={'--json','--offline','--override-channels','--strict-channel-priority',
              '--update-deps','--update-all','--freeze-installed','--prune','--dry-run','--no-pin'}
    output=['install'];channels=set(requested);specs=[];prefixes=[];i=2
    while i<len(argv):
        value=argv[i];i+=1
        if value in ('--yes','--download-only'):continue
        if value in switches:output.append(value);continue
        if value in ('-p','--solver','--channel'):
            if i==len(argv):raise RuntimeError('Incomplete saved command option: '+value)
            argument=argv[i];i+=1
            if value=='-p':prefixes.append(Path(argument).resolve())
            elif value=='--solver' and argument not in ('classic','libmamba'):raise RuntimeError('Unsupported saved solver')
            elif value=='--channel':
                if invalid_channel_reason(argument) or forbidden_channel(argument):raise RuntimeError('Invalid diagnostic channel')
                channels.add(argument)
            output.extend((value,argument));continue
        if value.startswith('-') or any(c in value for c in '\n\r\x00') or not re.fullmatch(r'(?:.+::)?[\w][\w.-]*(?:[<>=!~].*)?',value):
            raise RuntimeError('Unsupported saved install argument: '+repr(value))
        specs.append(value);output.append(value)
    if prefixes!=[prefix.resolve()] or '--override-channels' not in output or '--strict-channel-priority' not in output:
        raise RuntimeError('Saved command lacks the expected exact prefix and channel policy')
    if '--no-pin' in output and prefix.resolve()!=base.resolve():
        raise RuntimeError('Ignoring saved package pins is permitted only for the selected base')
    for spec in specs:
        if '::' in spec:
            origin=spec.rsplit('::',1)[0]
            if origin not in channels or forbidden_channel(origin):raise RuntimeError('Diagnostic package source outside saved channels')
    if not specs:raise RuntimeError('Saved command has no package specifications')
    if '--dry-run' not in output:output.append('--dry-run')
    if '--json' not in output:output.append('--json')
    return output


def diagnose_existing(directory, base, offline=False, timeout_seconds=600):
    if timeout_seconds<=0:raise ValueError('Diagnostic timeout must be a positive number of seconds')
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
    if '--solver' not in argv:raise RuntimeError('Saved command has no solver selection')
    argv[argv.index('--solver')+1]='libmamba'
    if offline and '--offline' not in argv:argv.append('--offline')
    print('DIAGNOSTIC DRY RUN: '+str(prefix),flush=True)
    print('Solver: installed libmamba; no classic conflict-hint analysis and no installed Conda file patches.',flush=True)
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
    env.update(CONDA_UNSATISFIABLE_HINTS='false',CONDA_DRY_RUN='true',PYTHONDONTWRITEBYTECODE='1',
               CONDA_OFFLINE='true' if '--offline' in argv else 'false')
    bundle=base/'etc/cse-trust/ca-bundle.pem';empty=base/'etc/cse-trust/empty-ca-dir'
    if not bundle.is_file() or not empty.is_dir():
        raise RuntimeError('The managed CA bundle/empty CA directory used by apply is unavailable; inspect trust before diagnosing package access')
    for key in ('CONDA_SSL_VERIFY','REQUESTS_CA_BUNDLE','SSL_CERT_FILE','CURL_CA_BUNDLE','PIP_CERT'):env[key]=str(bundle)
    if any(empty.iterdir()):raise RuntimeError('Expected dedicated empty CA directory')
    env['SSL_CERT_DIR']=str(empty)
    command=solver_invocation(base,[str(base/'bin/conda')]+argv)
    finished=threading.Event();started=time.monotonic()
    def progress():
        while not finished.wait(30):print('Still diagnosing dependencies (%ds elapsed)'%(time.monotonic()-started),flush=True)
    heartbeat=threading.Thread(target=progress,daemon=True);heartbeat.start()
    print('Running the saved request with its saved pin policy and strict channel priority; diagnostic limit %d seconds.'%timeout_seconds,flush=True)
    timed_out=False
    try:
        result=subprocess.run(command,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout_seconds)
        stdout,stderr,code=result.stdout,result.stderr,result.returncode
    except subprocess.TimeoutExpired as exc:
        timed_out=True
        def decoded(value):return value.decode(errors='replace') if isinstance(value,bytes) else (value or '')
        stdout,stderr,code=decoded(exc.stdout),decoded(exc.stderr)+'\nConflict diagnostics timed out after %d seconds.'%timeout_seconds,None
    except OSError as exc:
        stdout,stderr,code='',type(exc).__name__+': '+str(exc),None
    finally:finished.set();heartbeat.join()
    report=directory/('solver-diagnostic-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.json')
    payload={'argv':[str(base/'bin/conda')]+argv,'phase':record.get('phase'),'returncode':code,
             'stdout':stdout,'stderr':stderr,'prefix_access':access_snapshot(prefix),'dry_run':True,
             'diagnostic_status':'timed_out' if timed_out else ('command_error' if code is None else 'completed'),
             'timeout_seconds':timeout_seconds,'elapsed_seconds':round(time.monotonic()-started,2)}
    fd=os.open(str(report),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as stream:json.dump(payload,stream,indent=2)
    try:
        data=json.loads(stdout)
        if not isinstance(data,dict):raise ValueError('Expected JSON object')
        message=data.get('message') or diagnostic_text(stdout,stderr)
    except ValueError:
        data={};message=diagnostic_text(stdout,stderr)
    if timed_out:
        print('DIAGNOSTIC TIMED OUT after %d seconds; conflict analysis did not complete.'%timeout_seconds,flush=True)
        print('A deprecated version-spec warning is not a conflicting-package finding. No package transaction was attempted.',flush=True)
        print('Review the saved native solver output and explicit pins. Use the current script\'s retained base package inventory to revise the request.',flush=True)
        print('Partial Conda output:',flush=True)
    print(str(message)[:16000],flush=True)
    print('Full diagnostic: '+str(report),flush=True)
    solved=code==0 and data.get('success') is True
    print('Result: '+('diagnostic timed out; no conflict conclusion or package transaction' if timed_out else
                     'dry-run plan solved; no upgrade installed' if solved else 'solve/access failure; no package transaction attempted'))
    return 0 if solved else 2


def access_snapshot(path):
    """Read current access metadata; never chmod to make a check pass."""
    p = Path(os.path.abspath(os.path.expanduser(str(path))))
    def describe(candidate):
        entry = dict(path=str(candidate),**path_owner(candidate))
        try:
            st = candidate.lstat()
            entry.update(mode=stat.filemode(st.st_mode),octal='%04o'%stat.S_IMODE(st.st_mode),
                         symlink_target=str(candidate.resolve()) if stat.S_ISLNK(st.st_mode) else None,
                         sticky=bool(st.st_mode & stat.S_ISVTX))
            entry['access'] = {name:os.access(str(candidate),flag) for name,flag in
                              (('read',os.R_OK),('write',os.W_OK),('execute_or_traverse',os.X_OK))}
            try:
                entry['extended_acl'] = 'system.posix_acl_access' in os.listxattr(str(candidate)) if hasattr(os,'listxattr') else 'unknown'
            except OSError as exc: entry['extended_acl'] = 'unreadable: '+str(exc)
        except (OSError,RuntimeError) as exc: entry['stat_error'] = str(exc)
        return entry
    result = describe(p)
    result['captured_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    # Renaming/removing a directory entry requires access to its parent, even
    # when the file itself is writable. File ownership/mode alone is insufficient.
    result['parent_directory'] = describe(p.parent)
    result['blocked_parents'] = []
    for parent in p.parents:
        if not os.access(str(parent),os.X_OK):
            result['blocked_parents'].append(dict(path=str(parent),**path_owner(parent)))
    return result


def denied_paths(text):
    found = []
    patterns = (r"[Pp]ermission denied['\"]\s*,\s*['\"](/[^'\"]+)['\"]",
                r"[Pp]ermission denied:?\s*['\"]([^'\"]+)['\"]",
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
    parent = snapshot.get('parent_directory')
    if parent:
        say('    Containing directory: %s | owner=%s group=%s mode=%s | %s | ACL=%s | sticky=%s' % (
            parent['path'],parent['owner'],parent['group'],parent.get('mode','unknown'),
            parent.get('access',parent.get('stat_error','unknown')),parent.get('extended_acl','unknown'),parent.get('sticky','unknown')))
        say('    Rename/remove needs directory write and traversal access; sticky bits, ACLs and filesystem policy may also restrict it.')
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
        name=re.split(r'[<>=!~ ]',spec,maxsplit=1)[0]
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
    try: native=native_bundle_paths(base)
    except (OSError,RuntimeError) as exc:
        print('Native PEM discovery failed: '+str(exc));native=[]
    bundle=native[0] if native else base/'ssl/cacert.pem'
    good=bool(native)
    paths=native+[base/'etc/cse-trust/ca-bundle.pem']
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
            if path in native and present: good=False
        except FileNotFoundError:
            if path in native: good=False;print('Native bundle: ABSENT at '+str(path))
        except (OSError,ValueError,RuntimeError) as exc:
            print('Bundle check failed: %s | %s'%(path,exc))
            if path in native: good=False
            if isinstance(exc,PermissionError):print_access(access_snapshot(path),print)
    marker=base/'etc/cse-trust/managed-by-patch-miniforge-trust'
    try: print('Managed marker: '+marker.read_text().strip())
    except OSError as exc: print('Managed marker unavailable: '+str(exc))
    print('Current shell CA variables: '+json.dumps({k:os.environ[k] for k in ('CONDA_SSL_VERIFY','REQUESTS_CA_BUNDLE','SSL_CERT_FILE','CURL_CA_BUNDLE','PIP_CERT','SSL_CERT_DIR') if k in os.environ},sort_keys=True))
    selected=[k for k in ('CONDA_SSL_VERIFY','REQUESTS_CA_BUNDLE','SSL_CERT_FILE','CURL_CA_BUNDLE','PIP_CERT') if os.environ.get(k)==str(bundle)]
    print('Current shell variables selecting native PEM: '+(', '.join(selected) or 'NONE; native defaults or application-specific configuration may apply'))
    print('Native Miniforge bundle screening: '+('PRESENT, PARSEABLE, FOUR KNOWN ROOTS ABSENT' if good else 'NOT CONFIRMED'))
    print('Stored bundle, package versions and active application trust are separate. This does not prove full chain rejection or proxy remediation.')
    print('No changes, package updates or external TLS connections were made.')
    return 0 if good else 2


def promotion_differences(actual, expected):
    differences=set(actual)^set(expected)
    for name in set(actual)&set(expected):
        record=actual[name];target=expected[name]
        if any(record.get(key)!=target.get(key) for key in ('version','build','subdir')):
            differences.add(name);continue
        common=[key for key in ('sha256','md5') if record.get(key) and target.get(key)]
        if not common or any(record[key]!=target[key] for key in common):differences.add(name)
    return sorted(differences)


def permission_audit(base, directory=None, stage=None, ca_inputs=()):
    started=time.monotonic();finished=threading.Event()
    def heartbeat():
        while not finished.wait(30):print('Permission preflight is still scanning known paths (%ds elapsed)'%(time.monotonic()-started),flush=True)
    worker=threading.Thread(target=heartbeat,daemon=True);worker.start()
    try:return collect_permission_audit(base,directory,stage,ca_inputs)
    finally:finished.set();worker.join()


def collect_permission_audit(base, directory=None, stage=None, ca_inputs=()):
    """Collect known access blockers across packages; report only, never repair."""
    root=(directory or Path.home()/'.cse-trust-logs'/('permissions-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f'))).expanduser().resolve()
    if root==base or base in root.parents or root in base.parents or any((p/'conda-meta/history').is_file() for p in root.parents):
        raise RuntimeError('Permission reports must be outside Conda environments')
    root.mkdir(mode=0o700,parents=True,exist_ok=False);os.chmod(str(root),0o700)
    report=root/'permission-preflight';report.mkdir(mode=0o700)
    issues=[];meta={};blocks=[];record_files={}
    try:
        with os.scandir(base/'conda-meta') as entries:files=sorted(Path(e.path) for e in entries if e.name.endswith('.json'))
    except OSError as exc:
        files=[];issues.append({'path':str(base/'conda-meta'),'reason':'Cannot inventory package metadata: '+str(exc)})
    for path in files:
        try:
            record=json.loads(path.read_text())
            if not isinstance(record,dict) or not isinstance(record.get('name'),str) or not all(record.get(k) for k in ('name','version','build')):raise ValueError('Missing package identity')
            meta[record['name']]=record
            record_files[record['name']]=path
        except (OSError,ValueError,TypeError) as exc:
            issues.append({'path':str(path),'reason':'Cannot inventory this package metadata: '+str(exc)})
    start=len(issues);holds=permission_holds(base,meta,issues=issues)
    for issue in issues[start:]:
        if issue.get('package') in record_files:issue['path']=str(record_files[issue['package']])
    def append_holds(source,phase):
        for name,hold in source.items():
            for entry in hold.get('blocked_paths') or [{'path':hold['path'],'reason':hold['reason'],'blocking_path':str(Path(hold['path']).parent)}]:
                blocks.append(dict(entry,package=name,phase=phase))
    append_holds(holds,'installed package')
    proposed={}
    if stage:
        try:
            stage=stage.expanduser().resolve(strict=True)
            summary=json.loads((stage/'stage-summary.json').read_text())
            if Path(summary['source_base']).resolve()!=base:raise ValueError('Stage belongs to another base; load the intended environment/Miniforge')
            proposed=json.loads((stage/'candidate-packages.json').read_text())
            if not isinstance(proposed,dict):raise ValueError('Candidate inventory must be a package mapping')
            valid={}
            for name,record in proposed.items():
                if not isinstance(record,dict) or record.get('name')!=name or not all(record.get(k) for k in ('version','build')):
                    issues.append({'path':str(stage/'candidate-packages.json'),'package':name,'reason':'Cannot inspect malformed candidate package identity'})
                else:valid[name]=record
            proposed=valid
            start=len(issues)
            append_holds(permission_holds(base,proposed,issues=issues,include_directories=True),'candidate package')
            for issue in issues[start:]:issue['path']=str(stage/'candidate-packages.json')
        except (OSError,ValueError,TypeError,KeyError,RuntimeError) as exc:
            proposed={}
            issues.append({'path':str(stage),'reason':'Cannot inspect proposed package paths: '+str(exc)})
    def control(path,flags,operation,optional=False):
        try:
            exists=path.exists()
            if exists and os.access(str(path),flags):return
            if not exists and optional:
                parent=path.parent
                while parent!=base.parent:
                    try:
                        parent.lstat();break
                    except FileNotFoundError:parent=parent.parent
                if os.access(str(parent),os.W_OK|os.X_OK):return
                target=first_blocked_parent(base,path) or parent
                reason='Cannot create control path: parent lacks write/traverse access'
            else:
                target=first_blocked_parent(base,path) or path
                reason='Required '+operation+' access is unavailable'+(' (path missing)' if not exists else '')
            blocks.append({'path':str(path),'blocking_path':str(target),'reason':reason,'package':'<base controls>',
                           'phase':operation,'exists':exists})
        except OSError as exc:
            blocks.append({'path':str(path),'blocking_path':str(first_blocked_parent(base,path) or path),
                           'reason':str(exc),'package':'<base controls>','phase':operation,'exists':None})
    for path,flags,operation,optional in (
        (base,os.R_OK|os.W_OK|os.X_OK,'base directory read/write/traverse',False),
        (base/'conda-meta',os.R_OK|os.W_OK|os.X_OK,'metadata directory read/write/traverse',False),
        (base/'conda-meta/history',os.R_OK|os.W_OK,'history read/write',False),
        (base/'.condarc',os.R_OK|os.W_OK,'configuration read/write',True),
        (base/'conda-meta/state',os.R_OK|os.W_OK,'activation state read/write',True),
        (base/'bin/python',os.R_OK|os.X_OK,'Python bootstrap read/execute',False),
        (base/'bin/conda',os.R_OK,'Conda entry point read',False),
        (base/'etc/cse-trust',os.R_OK|os.W_OK|os.X_OK,'trust directory read/write/traverse',True),
        (base/'etc/cse-trust/maintenance.lock',os.R_OK|os.W_OK,'maintenance lock read/write',True),
        (base/'etc/cse-trust/ca-bundle.pem',os.R_OK,'existing trust bundle read',True),
        (base/'etc/cse-trust/use-ca.sh',os.R_OK,'existing trust snippet read',True)):
        control(path,flags,operation,optional)
    if stage:control(stage/'pkgs',os.R_OK|os.W_OK|os.X_OK,'stage cache read/write/traverse',True)
    for source in ca_inputs:control(Path(os.path.abspath(str(source.expanduser()))),os.R_OK,'explicit CA source read')
    for issue in issues:
        path=Path(issue['path']);blocks.append(dict(issue,blocking_path=str(first_blocked_parent(base,path) or path),
            package=issue.get('package','<unknown inventory>'),phase='inspection gap',exists=None))
    merged={};targets={}
    for block in blocks:
        key=(block['package'],block['path'],block['blocking_path'],block['reason'])
        if key not in merged:merged[key]=dict(block,phases=[])
        if block['phase'] not in merged[key]['phases']:merged[key]['phases'].append(block['phase'])
    rows=list(merged.values())
    for row in rows:
        name=row['package']
        row['required_for_promotion']=not stage or name.startswith('<') or name not in meta or name not in proposed or (
            meta[name].get('version'),meta[name].get('build'))!=(proposed[name].get('version'),proposed[name].get('build'))
        path=row['blocking_path']
        if path not in targets:
            access=access_snapshot(path)
            opaque=access.get('mode','').startswith('l') or (not access.get('access',{}).get('execute_or_traverse',True) and access.get('mode','').startswith('d'))
            advice='Owner/admin should review the named path access/ACL and the reported operation; then rerun this audit. No automatic chmod or deletion was performed.'
            if Path(path).name=='__pycache__':
                parent_record=access.get('parent_directory',{});parent=parent_record.get('access',{})
                sticky_ok=not parent_record.get('sticky') or os.geteuid() in (0,parent_record.get('uid'),access.get('uid'))
                if parent.get('write') and parent.get('execute_or_traverse') and sticky_ok:
                    advice+=' Its parent is writable and traversable: preserving the old cache directory by rename and creating a fresh shared cache may be a workaround after verifying its contents are disposable generated caches; filesystem policy may still restrict it.'
                    if opaque:advice+=' The contents could not be inspected; owner/admin review is required before treating them as disposable.'
            targets[path]={'path':path,'access':access,'owner':access['owner'],'uid':access['uid'],'group':access['group'],
                           'affected_packages':[],'affected_paths':[],'reasons':[],'uninspected_contents':opaque,'advice':advice}
        target=targets[path]
        for field,value in (('affected_packages',row['package']),('affected_paths',row['path'])):
            if value not in target[field]:target[field].append(value)
        if row['reason'] not in target['reasons']:target['reasons'].append(row['reason'])
    by_owner={}
    for target in targets.values():by_owner.setdefault(target['owner'],[]).append(target)
    opaque_paths=[p for p,t in targets.items() if t['uninspected_contents']]
    gap_paths={p['path'] for p in issues}|set(opaque_paths)
    result={'base':str(base),'report_directory':str(report),'captured_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'installed_packages_inspected':len(meta),'candidate_packages_inspected':len(proposed),'affected_path_count':len(rows),
            'repair_target_count':len(targets),'inspection_gaps':issues,'inspection_gap_count':len(gap_paths),
            'uninspected_directories':opaque_paths,'targets':list(targets.values()),
            'promotion_blocking_path_count':sum(r['required_for_promotion'] for r in rows),
            'status':'blocked' if rows else 'no-detected-blockers','source_changes_attempted':False,
            'coverage':'Known installed manifest paths, source-associated caches, optional candidate paths and base controls; inaccessible contents/untracked files, immutable flags, server policy and future changes cannot be fully proved by this read-only audit.'}
    old_umask=os.umask(0o077)
    try:
        (report/'permissions.json').write_text(json.dumps({'summary':result,'paths':rows},indent=2))
        (report/'permissions-by-owner.json').write_text(json.dumps(by_owner,indent=2))
        def lines(items):
            output=[]
            for item in items:
                a=item['access'];output+=['%s | owner=%s uid=%s group=%s mode=%s'%(item['path'],item['owner'],item['uid'],item['group'],a.get('mode','unknown')),
                    '  Packages: '+', '.join(item['affected_packages']),'  Reasons: '+'; '.join(item['reasons']),
                    '  Effective access: '+str(a.get('access',a.get('stat_error','unknown'))),
                    '  ACL: '+str(a.get('extended_acl','unknown')),'  Uninspected directory contents: '+str(item['uninspected_contents']),
                    '  Advice: '+item['advice']]
                output.extend('    '+p for p in item['affected_paths'])
            return '\n'.join(output)+'\n'
        (report/'permissions.txt').write_text('Read-only permission preflight; source was not modified.\n'+result['coverage']+'\n\n'+lines(targets.values()))
        for owner,items in by_owner.items():
            uid=items[0]['uid'];(report/('permissions-owner-%s.txt'%(uid if uid is not None else 'unknown'))).write_text(lines(items))
        with (report/'permissions.csv').open('w',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=['package','path','blocking_path','owner','uid','group','file_uid','file_gid','reason','exists','required_for_promotion','phases'])
            writer.writeheader()
            for row in rows:
                target=targets[row['blocking_path']]
                writer.writerow({key:(', '.join(row['phases']) if key=='phases' else target[key] if key in ('owner','uid','group') else row.get(key,'')) for key in writer.fieldnames})
        (root/'permission-summary.json').write_text(json.dumps(result,indent=2))
    finally:os.umask(old_umask)
    print('Permission preflight: %s | %d affected paths | %d repair targets | %d inspection gaps'%(
        result['status'],len(rows),len(targets),len(gap_paths)),flush=True)
    print('Full owner/group report: '+str(report/'permissions.txt'),flush=True)
    print('Reports for owner review: '+str(report/'permissions-by-owner.json')+' and permissions-owner-UID.txt',flush=True)
    print('This scan covers known paths; hidden contents and future filesystem/runtime restrictions may require a later check.',flush=True)
    return {'root':root,'summary':result,'holds':holds}


def load_promotion(directory, base, holds=None):
    root=directory.expanduser().resolve(strict=True)
    if base==root or base in root.parents or root in base.parents:
        raise RuntimeError('Reviewed stage must be outside the live base')
    summary=json.loads((root/'stage-summary.json').read_text())
    if summary.get('status')!='ready-for-review' or summary.get('source_metadata_unchanged') is not True or summary.get('source_ca_unchanged') is not True:
        raise RuntimeError('Promotion requires a ready-for-review stage with unchanged source metadata and CA')
    if Path(summary['source_base']).resolve()!=base:
        raise RuntimeError('This stage belongs to '+summary['source_base']+', not '+str(base)+'. Load the correct site environment/Miniforge, or stage this system separately.')
    if stage_source_state(base)!=summary['source_state_after']:
        raise RuntimeError('Base package/control metadata changed since staging; stage and review this system again')
    packages=json.loads((root/'candidate-packages.json').read_text())
    if not {'curl','libcurl'}<=set(packages):
        raise RuntimeError('Reviewed candidate lacks the required curl/libcurl pair. Restage an unpromoted candidate with revision 30; for an already-updated base use --repair-curl instead.')
    if not packages or not {'conda','python','conda-libmamba-solver'}<=set(packages):raise RuntimeError('Reviewed candidate lacks its required Conda/Python/solver packages')
    for name,record in packages.items():
        if record.get('name')!=name or not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]*',name):raise RuntimeError('Invalid reviewed package name: '+str(name))
        if any(not re.fullmatch(r'[A-Za-z0-9_.+!-]+',str(record.get(key,''))) for key in ('version','build')):raise RuntimeError('Invalid reviewed version/build: '+name)
        hashes=[key for key,size in (('sha256',64),('md5',32)) if re.fullmatch(r'[0-9a-f]{%d}'%size,str(record.get(key,'')))]
        if any(record.get(key) and not re.fullmatch(r'[0-9a-f]{%d}'%size,str(record[key])) for key,size in (('sha256',64),('md5',32))):
            raise RuntimeError('Malformed reviewed package checksum: '+name)
        if not hashes or not record.get('subdir'):raise RuntimeError('Reviewed package lacks platform/checksum metadata: '+name)
        if not recorded_origin(record) or any(forbidden_channel(record.get(key,'')) for key in ('channel','url','base_url')):
            raise RuntimeError('Reviewed package has an excluded or unidentified source: '+name)
    plan=json.loads((root/'candidate-plan.json').read_text())
    check_plan(plan,None,set(packages))
    expected={r['name']:(r['version'],r.get('build_string') or r.get('build')) for r in plan.get('actions',{}).get('LINK',[])}
    verify_installed_plan(expected,packages)
    verify_retained(expected,summary['requested_roots'])
    target=max((CONDA_MINIMUM,summary.get('conda_update',{}).get('target',CONDA_MINIMUM)),key=version)
    verification=verify_minimums(packages,packages,True,target)
    if (root/'env/conda-meta').is_dir():
        differences=promotion_differences(records(root/'env'),packages)
        if differences:raise RuntimeError('Staged candidate changed after review: '+', '.join(differences))
    before=records(base)
    if holds is None:holds=permission_holds(base,before)
    blocked=[h for n,h in holds.items() if n not in packages or
             (before[n]['version'],before[n]['build'])!=(packages[n]['version'],packages[n]['build'])]
    if blocked:
        raise RuntimeError('Reviewed promotion requires owner/admin access repair before any base changes: '+
                           '; '.join('%s: %s (%s)'%(h['name'],h['path'],h['reason']) for h in blocked))
    identity={n:{key:r.get(key) for key in ('version','build','subdir','sha256','md5')} for n,r in sorted(packages.items())}
    digest=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
    return {'root':root,'summary':summary,'packages':packages,'identity':identity,'manifest_sha256':digest,
            'security_verification':verification,'target':target}


def stage_source_state(base, meta=None):
    """Fingerprint source package records and control files without changing them."""
    if meta is None:meta=records(base)
    controls={}
    for name in ('.condarc','conda-meta/history','conda-meta/pinned','conda-meta/state',
                 'etc/cse-trust/ca-bundle.pem','etc/cse-trust/use-ca.sh'):
        try:controls[name]=hashlib.sha256((base/name).read_bytes()).hexdigest()
        except FileNotFoundError:controls[name]=None
        except OSError as exc:controls[name]={'unreadable':str(exc)}
    return {'packages':hashlib.sha256(json.dumps(meta,sort_keys=True).encode()).hexdigest(),'controls':controls}


def stage_requests(meta, intent, skipped, conda_minimum):
    protected=set(MINIMUM)|{'conda','python','conda-libmamba-solver','curl'}
    unknown=set(skipped)-set(meta)-set(intent['roots'])
    if unknown-protected:raise RuntimeError('Unknown --stage-skip package(s): '+', '.join(sorted(unknown-protected)))
    if set(skipped)&protected:raise RuntimeError('Cannot omit required Conda/Python/security packages: '+', '.join(sorted(set(skipped)&protected)))
    omitted=set(skipped)
    for migration in intent['replacements']:
        if migration['name'] in omitted:omitted.update(migration['replacements'])
    roots=(set(intent['roots'])|{'conda','python','conda-libmamba-solver','curl'})-omitted
    specs=[n+'>='+MINIMUM[n] if n in MINIMUM else ('conda>='+conda_minimum if n=='conda' else n) for n in sorted(roots)]
    return roots,specs,omitted


def stage_comparison(before, after, original_roots, requested, omitted, ready):
    rows=[]
    for name in sorted(set(before)|set(after)|set(original_roots)):
        old=before.get(name,{});new=after.get(name,{})
        if not new:status='not-selected' if ready else 'not-installed'
        elif not old:status='added'
        elif old['version']!=new['version']:status='changed-version'
        elif old['build']!=new['build']:status='changed-build'
        else:status='unchanged'
        note=''
        if name in omitted:note='Request explicitly omitted; it may still be required as a dependency.'
        elif not new and ready:note='Not selected by the new dependency graph; this does not establish unavailability.'
        if not ready:note+=' Candidate is not verified; a joint solve failure does not establish individual package availability.'
        rows.append({'package':name,'before_version':old.get('version',''),'before_build':old.get('build',''),
                     'after_version':new.get('version',''),'after_build':new.get('build',''),'status':status,
                     'role':'requested' if name in requested else 'original-request' if name in original_roots else 'dependency',
                     'note':note.strip()})
    return rows


def validate_change_inventory(data):
    if not isinstance(data,dict):raise RuntimeError('Package inventory must be a mapping')
    for name,record in data.items():
        if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]*',name) or not isinstance(record,dict) or not all(isinstance(record.get(key),str) and record[key] for key in ('version','build')):
            raise RuntimeError('Incomplete package version/build identity in saved inventory: '+str(name))
    return data


def write_package_changes(destination, before, after, details, rows=None):
    """Write only public package identities, never private inventories or logs."""
    destination=Path(destination).expanduser().resolve()
    if destination.exists():raise RuntimeError('Choose a new change-list directory; existing output is not overwritten')
    if any((parent/'conda-meta/history').exists() for parent in destination.parents):
        raise RuntimeError('Change lists must be outside Conda environments')
    if rows is None:
        validate_change_inventory(before);validate_change_inventory(after)
        rows=stage_comparison(before,after,(),(),(),True)
        for row in rows:
            if row['status']=='not-selected' and details['evidence']!='candidate-only':row['status']='removed'
        rows=[{key:row[key] for key in ('package','before_version','before_build','after_version','after_build','status')} for row in rows]
    manifest=dict(details,generated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  counts={status:sum(row['status']==status for row in rows) for status in sorted({row['status'] for row in rows})},
                  scope='Conda-managed packages only; native PEM filtering and user-operation verification are separate records.')
    destination.mkdir(mode=0o755,parents=True,exist_ok=False)
    fields=['package','before_version','before_build','after_version','after_build','status']
    (destination/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (destination/'packages.json').write_text(json.dumps(rows,indent=2)+'\n')
    with (destination/'packages.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    escape=lambda value:str(value).replace('|','\\|').replace('`','\\`').replace('\n',' ')
    heading='NOT INSTALLED: candidate package comparison' if manifest['evidence']=='candidate-only' else 'Miniforge base package changes'
    lines=['# '+heading,'','Evidence: **'+escape(manifest['evidence'])+'**',
           '','Coverage: '+escape(manifest.get('coverage','full inventory')),
           '','Recorded rollout status: '+escape(manifest.get('rollout_status','not recorded')),
           '','Installation: `'+escape(manifest.get('prefix','not recorded'))+'`',
           '','Report generated: '+manifest['generated_at']+' (this is not the installation time).',
           '','Counts: '+(', '.join('%s=%d'%item for item in manifest['counts'].items()) or 'no recorded changes'),
           '','Version changes are not necessarily upgrades. A build change can keep the same version.',
           'This list is package evidence, not a sign-off for permissions, certificates or all user applications.',
           'Pip-installed applications and manual PEM edits are outside this package inventory.']
    if manifest.get('note'):lines+=['',escape(manifest['note'])]
    for changed in (True,False):
        subset=[row for row in rows if (row['status']!='unchanged')==changed]
        lines+=['','## '+('Changes' if changed else 'Unchanged packages'),'']
        if not subset:lines+=['None recorded.' if changed else 'No unchanged package records available in this report.'];continue
        lines+=['| Package | Before version | Before build | After version | After build | Result |',
                '| --- | --- | --- | --- | --- | --- |']
        lines+=['| '+' | '.join(escape(row[key]) or '—' for key in fields)+' |' for row in subset]
    (destination/'README.md').write_text('\n'.join(lines)+'\n')
    for name in ('README.md','packages.csv','packages.json','manifest.json'):(destination/name).chmod(0o644)
    destination.chmod(0o755)
    return manifest


def export_package_changes(source, destination=None):
    source=report_directory(source)
    destination=destination or source/'user-changes'
    if (source/'stage-summary.json').is_file():
        stage=json.loads((source/'stage-summary.json').read_text())
        if stage.get('status')!='ready-for-review':raise RuntimeError('Candidate is incomplete; insufficient evidence for a complete comparison')
        before=json.loads((source/'source-packages.json').read_text());after=json.loads((source/'candidate-packages.json').read_text())
        details={'evidence':'candidate-only','coverage':'full candidate comparison','prefix':stage['source_base'],
                 'rollout_status':stage['status'],'note':'NOT INSTALLED: this stage report does not establish a completed shared-base update.'}
        manifest=write_package_changes(destination,before,after,details)
    else:
        rows=json.loads((source/'summary.json').read_text())
        if len(rows)!=1:raise RuntimeError('Export requires a report for one installation; mixed-prefix historical reports need separate review')
        row=rows[0];mode=(source/'run.log').read_text() if (source/'run.log').is_file() else ''
        if 'Mode: APPLY' not in mode:raise RuntimeError('No verified installed transaction is recorded; this may be a preview')
        before_file=source/'000-before-packages.json';after_file=source/'000-after-packages.json'
        details={'prefix':row['prefix'],'rollout_status':row['status']}
        if row.get('package_inventory_verified') and before_file.is_file() and after_file.is_file():
            before=json.loads(before_file.read_text());after=json.loads(after_file.read_text())
            details.update(evidence='verified-installed',coverage='full inventory',note='Compared recorded before/after inventories after installed-package verification. Overall rollout status is recorded separately.')
            manifest=write_package_changes(destination,before,after,details)
        elif row.get('changes_started') and row.get('promotion',{}).get('status') in ('packages-verified','completed'):
            guard=json.loads((source/'approved-promotion-plan.json').read_text())
            identity=guard['packages'];digest=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
            if guard['prefix']!=row['prefix'] or digest!=row['promotion']['manifest_sha256']:
                raise RuntimeError('Saved promotion identity does not match the verified run')
            before={name:{'version':values[0],'build':values[1]} for name,values in guard['before'].items()}
            details.update(evidence='verified-installed',coverage='full inventory',note='Reconstructed from the saved approved manifest and recorded successful package verification; no current live installation was inspected.')
            manifest=write_package_changes(destination,before,identity,details)
        elif row.get('status','').startswith('updated'):
            changes=[]
            for item in row.get('package_changes',()):
                added=item['before']=='absent'
                changes.append({'package':item['name'],'before_version':'' if added else item['before'],'before_build':'',
                    'after_version':item['after'],'after_build':'','status':'added' if added else 'changed-version' if item['before']!=item['after'] else 'changed-build'})
            for item in row.get('package_removals',()):
                if item.get('status')=='verified':changes.append({'package':item['name'],'before_version':item.get('before',''),
                    'before_build':'','after_version':'','after_build':'','status':'removed'})
            details.update(evidence='limited-installed-summary',coverage='partial recorded changes; unchanged inventory unavailable',
                           note='Older successful run summary only. Build identifiers and unrecorded changes are unavailable; blank fields mean unknown, not a missing package.')
            manifest=write_package_changes(destination,{}, {},details,rows=changes)
        else:raise RuntimeError('No verified installed inventory; insufficient evidence to publish completed changes')
    print('Package change list: '+str(Path(destination).expanduser().resolve()/'README.md'))
    print('Evidence: '+manifest['evidence']+' | coverage: '+manifest['coverage'])
    print('Share only the generated files after review, from a location users can read. No packages or current base files were inspected or changed.')
    return 0


def write_stage_report(root, summary, before, after):
    rows=stage_comparison(before,after,summary.get('original_roots',()),summary.get('requested_roots',()),
                          summary.get('omitted_requests',()),summary['status']=='ready-for-review')
    summary['comparison_counts']={s:sum(r['status']==s for r in rows) for s in sorted({r['status'] for r in rows})}
    (root/'comparison.json').write_text(json.dumps(rows,indent=2))
    with (root/'comparison.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=['package','before_version','before_build','after_version','after_build','status','role','note'])
        writer.writeheader();writer.writerows(rows)
    (root/'stage-summary.json').write_text(json.dumps(summary,indent=2))
    escape=lambda value:str(value).replace('|','\\|').replace('\n',' ')
    lines=['# Private base candidate review','',
           'Status: **'+summary['status']+'**','',
           'Source base: `'+summary['source_base']+'`',
           'Candidate prefix: `'+summary['candidate_prefix']+'`','',
           'No promotion to the shared base was performed. The candidate must remain at its current prefix; it is not a relocatable replacement.',
           'This comparison covers Conda-managed packages. Pip-installed applications are not automatically recreated.',
           'Source package/control metadata unchanged: '+str(summary.get('source_metadata_unchanged','not checked'))+'.','',
           'Counts: '+', '.join('%s=%d'%item for item in summary['comparison_counts'].items()),'',
           'Version changes show the actual before/after values; they do not assert that every change is an upgrade.',
           'Not-selected dependencies are not findings of deprecation or unavailability.','']
    if summary.get('omitted_requests'):lines+=['Explicitly omitted requests: '+', '.join(summary['omitted_requests']), '']
    if summary.get('non_conda_tools'):
        lines+=['Runtime tools outside the source Conda inventory (not automatically recreated): '+
                ', '.join('%s=%s'%item for item in sorted(summary['non_conda_tools'].items())), '']
    if summary.get('source_permission_holds'):
        lines+=['## Source access blockers','',
                'These holds were not applied in the fresh private candidate. They still matter if a later update must replace files in the live base.','']
        lines.extend('- `%s=%s=%s`: `%s` (%s)'%(h['name'],h['version'],h['build'],h['path'],h['reason']) for h in summary['source_permission_holds'])
        lines.append('')
    if summary['issues']:lines+=['## Issues','']+['- '+escape(issue) for issue in summary['issues']]+['']
    lines+=['## Package comparison','','| Package | Source version / build | Candidate version / build | Result | Role |',
            '| --- | --- | --- | --- | --- |']
    for row in rows:
        old=' / '.join(filter(None,(row['before_version'],row['before_build']))) or 'absent'
        new=' / '.join(filter(None,(row['after_version'],row['after_build']))) or 'absent'
        lines.append('| '+' | '.join(map(escape,(row['package'],old,new,row['status'],row['role'])))+' |')
    lines+=['','See comparison.csv / comparison.json for per-package notes and command-*.json for complete solver/transaction output.',
            'A failed candidate can contain partial files. Only ready-for-review means the complete installed plan and required minimums were verified.','']
    (root/'review.md').write_text('\n'.join(lines))


def report_stage_existing(root, verbose=False):
    summary=json.loads((root/'stage-summary.json').read_text())
    rows=json.loads((root/'comparison.json').read_text())
    print('READ-ONLY PRIVATE CANDIDATE REPORT: '+str(root))
    print('Captured status: '+summary['status'])
    print('Source base: '+summary['source_base'])
    print('Candidate prefix: '+summary['candidate_prefix'])
    print('Source metadata unchanged at end of staging: '+str(summary.get('source_metadata_unchanged','not checked')))
    print('Comparison: '+', '.join('%s=%s'%item for item in summary['comparison_counts'].items()))
    for row in rows:
        if row['status']=='unchanged' and not verbose:continue
        print('  %s | %s=%s -> %s=%s | %s | %s'%(row['package'],row['before_version'] or 'absent',row['before_build'],
              row['after_version'] or 'absent',row['after_build'],row['status'],row['note']))
    for issue in summary['issues']:print('  Issue: '+issue)
    print('Full review: '+str(root/'review.md'))
    print('No updates, network requests or promotion performed. This is the saved staging result, not a current source or runtime check.')
    return 0


def stage_base(args, base, env):
    """Build a fresh private candidate. Never update, clone or configure the source."""
    destination=args.stage.expanduser()
    if destination.exists() or destination.is_symlink():raise RuntimeError('Stage directory must be new; retain old candidates for comparison: '+str(destination))
    root=destination.resolve()
    if root.exists() or root.is_symlink():raise RuntimeError('Stage directory must be new; retain old candidates for comparison: '+str(root))
    if root==base or base in root.parents or root in base.parents:
        raise RuntimeError('Stage directory must be outside the source installation and its ancestors')
    if any((p/'conda-meta/history').is_file() for p in root.parents):
        raise RuntimeError('Stage directory must be outside existing Conda environments')
    if any(c in str(root) for c in (os.pathsep,',','\n')):
        raise RuntimeError('Stage path contains a Conda environment-variable path delimiter')
    old_umask=os.umask(0o077)
    try:root.mkdir(mode=0o700,parents=True,exist_ok=False)
    except BaseException:
        os.umask(old_umask);raise
    candidate=root/'env';before={};after={};source=None;source_digest=None;baseline=None
    summary={'script_revision':SCRIPT_REVISION,'source_base':str(base),'candidate_prefix':str(candidate),
             'started_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
             'status':'preparing','phase':'prepare private stage','issues':[],'promotion_performed':False,'commands':[]}
    env=dict(env,CONDA_PKGS_DIRS=str(root/'pkgs'),CONDA_ENVS_PATH=str(root/'environments'),
             CONDA_REGISTER_ENVS='false',CONDA_SHORTCUTS='false',PYTHONDONTWRITEBYTECODE='1',
             CONDA_NUMBER_CHANNEL_NOTICES='0',CONDA_REPORT_ERRORS='false',CONDA_AUTO_UPDATE_CONDA='false',
             CONDA_NOTIFY_OUTDATED_CONDA='false')
    for key,name in (('TMPDIR','tmp'),('XDG_CACHE_HOME','user-cache'),('XDG_CONFIG_HOME','user-config'),
                     ('XDG_DATA_HOME','user-data'),('XDG_STATE_HOME','user-state')):
        env[key]=str(root/name)
    env.pop('CSE_CONDA_PERMISSION_HOLDS',None)
    env.pop('CSE_CONDA_APPROVED_PLAN',None)
    for key in list(env):
        if re.fullmatch(r'CONDA_PREFIX(?:_\d+)?',key) or key in ('CONDA_EXE','CONDA_PYTHON_EXE','CONDA_DEFAULT_ENV',
                'CONDA_SHLVL','CONDA_PROMPT_MODIFIER','CONDA_ROOT_PREFIX','MAMBA_ROOT_PREFIX'):
            env.pop(key,None)
    try:log=(root/'run.log').open('w',buffering=1)
    except BaseException:
        os.umask(old_umask);raise
    def say(value):print(value,flush=True);log.write(value+'\n')
    def run(values, phase, runtime=base, raw=False, program=None):
        summary['phase']=phase;say('Staging: '+phase)
        argv=[str(runtime/'bin/python'),'-I','-B','-c',program or LIBMAMBA_CLI]+([] if program else list(map(str,values)))
        limit=None if values[0]=='create' and '--dry-run' not in values else (180 if values[0]=='search' or '--dry-run' in values else 30)
        started=time.monotonic();finished=threading.Event()
        def progress():
            while not finished.wait(30):say('Still staging: %s (%ds elapsed)'%(phase,time.monotonic()-started))
        heartbeat=threading.Thread(target=progress,daemon=True);heartbeat.start()
        stdout=stderr='';code=None
        try:
            result=subprocess.run(argv,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=limit)
            stdout,stderr,code=result.stdout,result.stderr,result.returncode
        except subprocess.TimeoutExpired as exc:
            decode=lambda v:v.decode(errors='replace') if isinstance(v,bytes) else v or ''
            stdout,stderr=decode(exc.stdout),decode(exc.stderr)
            raise RuntimeError('Private planning timed out after %ss; no candidate transaction attempted. '%limit+diagnostic_text(stdout,stderr)) from exc
        finally:
            finished.set();heartbeat.join()
            name='command-%03d.json'%(len(summary['commands'])+1)
            (root/name).write_text(json.dumps({'phase':phase,'argv':list(map(str,values)),'runtime':str(runtime),
                                             'returncode':code,'stdout':stdout,'stderr':stderr},indent=2))
            summary['commands'].append({'phase':phase,'file':name,'returncode':code})
        if code:raise RuntimeError(diagnostic_text(stdout,stderr)+' | complete output: '+str(root/name))
        if raw:return stdout
        try:data=json.loads(stdout)
        except ValueError as exc:raise RuntimeError('Invalid Conda JSON; see '+str(root/name)) from exc
        if isinstance(data,dict) and data.get('success') is False:raise RuntimeError(diagnostic_text(stdout,stderr))
        if isinstance(data,dict) and data.get('dry_run') and values[0]=='create' and '--dry-run' not in values:
            raise RuntimeError('Candidate creation returned a dry run; no installation verified')
        return data
    try:
        say('PRIVATE STAGING ONLY: '+str(root))
        say('Source base is read only; candidate, package cache, trust files and reports stay under this private directory.')
        for key in ('TMPDIR','XDG_CACHE_HOME','XDG_CONFIG_HOME','XDG_DATA_HOME','XDG_STATE_HOME'):
            Path(env[key]).mkdir(mode=0o700)
        before=records(base);baseline=stage_source_state(base,before)
        summary['source_state_before']=baseline
        (root/'source-packages.json').write_text(json.dumps(before,indent=2))
        config=run(['config','--show','--json'],'read source configuration')
        package_config={k:v for k,v in config.items() if k!='pinned_packages'}
        _,urls,channel_args,origins,excluded,unknown=environment_channels(before,args.channel,package_config)
        summary.update(channels=urls,excluded_sources=excluded,unknown_origins=unknown)
        source=choose_source(args,config,base);source_digest=hashlib.sha256(source.read_bytes()).hexdigest()
        text,removed=filtered_bundle([source]+args.extra_ca)
        trust=root/'trust';trust.mkdir(mode=0o700);bundle=trust/'ca-bundle.pem';bundle.write_text(text)
        empty=trust/'empty-ca-dir';empty.mkdir(mode=0o700)
        summary.update(source_ca=str(source),source_ca_sha256=source_digest,filtered_roots=removed)
        values={k:str(bundle) for k in ('CONDA_SSL_VERIFY','REQUESTS_CA_BUNDLE','SSL_CERT_FILE','CURL_CA_BUNDLE','PIP_CERT')}
        values['SSL_CERT_DIR']=str(empty);env.update(values)
        env['CONDA_OFFLINE']='true' if args.offline else 'false'
        intent=base_package_intent(before,base,config,ignore_pins=True)
        summary['intent']=intent
        summary['original_roots']=sorted(set(intent['roots'])|{'conda','python','conda-libmamba-solver'})
        summary['source_permission_holds']=list(permission_holds(base,before).values())
        probe=run(['__cse_solver_probe__'],'load installed libmamba solver')
        if probe.get('solver')!='libmamba':raise RuntimeError('Installed libmamba solver is unavailable')
        source_audit=run(['<local Python audit>'],'inventory source runtime tools',program=AUDIT)
        (root/'source-python-audit.json').write_text(json.dumps(source_audit,indent=2))
        summary['non_conda_tools']={n:r for n,r in source_audit.get('packages',{}).items() if n not in before}
        summary['conda_update']=conda_update_status(before)
        search_origins=dict(origins)
        if args.offline:
            mirrors=[url for url in urls if url.startswith('file://')]
            if not mirrors:raise RuntimeError('A fresh offline stage needs an approved --channel file:///mirror containing Conda and the requested packages; the source cache is not reused')
            search_origins['conda']=mirrors[0]
        target=select_conda_target(base,before,search_origins,config,args.offline,
            lambda command:run(command[1:],'find newest stable Conda'),root,summary,say,candidate_prefix=candidate)
        requested,specs,omitted=stage_requests(before,intent,args.stage_skip,target)
        summary.update(requested_roots=sorted(requested),omitted_requests=sorted(omitted))
        (root/'candidate-requests.txt').write_text('\n'.join(specs)+'\n')
        (root/'source-explicit.txt').write_text(run(['list','-p',str(base),'--explicit'],'record source package URLs',raw=True))
        common=['create','-p',str(candidate),'--solver','libmamba','--json','--no-pin','--no-default-packages','--no-shortcuts']+channel_args
        if args.offline:common.append('--offline')
        summary['status']='solving'
        plan=run(common+specs+['--dry-run'],'solve fresh candidate (dry run)')
        (root/'candidate-plan.json').write_text(json.dumps(plan,indent=2))
        if plan.get('actions',{}).get('PREFIX',str(candidate))!=str(candidate):raise RuntimeError('Candidate plan targets another prefix')
        check_plan(plan,None,requested)
        final,exact=exact_plan_specs({},plan,{},args.channel,package_config)
        verify_retained(final,requested)
        verify_minimums(before,{n:{'version':v} for n,(v,b) in final.items()},True,target)
        summary['status']='installing'
        run(common+exact+['--yes'],'install exact candidate plan')
        summary['status']='verifying';after=records(candidate)
        (root/'candidate-packages.json').write_text(json.dumps(after,indent=2))
        verify_installed_plan(final,after)
        summary['security_verification']=verify_minimums(before,after,True,target)
        summary['curl_runtime']=run(['<local curl probe>'],'verify candidate curl executable and loaded libcurl',runtime=candidate,program=CURL_PROBE)
        if run(['__cse_solver_probe__'],'verify candidate Conda and solver',runtime=candidate).get('solver')!='libmamba':
            raise RuntimeError('Candidate Conda/solver startup did not pass')
        audit=run(['<local Python audit>'],'verify candidate runtime packages and bundles',runtime=candidate,program=AUDIT)
        (root/'candidate-python-audit.json').write_text(json.dumps(audit,indent=2))
        for name,current in audit.get('packages',{}).items():
            if name in MINIMUM and version(current)<version(MINIMUM[name]):raise RuntimeError('Candidate runtime package below minimum: '+name)
        for label,path in audit.get('bundles',{}).items():
            if path and Path(path).is_file() and {h for h,pem in pem_entries(Path(path).read_text())}&set(ROOTS):
                raise RuntimeError('Known incident roots remain in candidate '+label+': '+path)
        run(['config','--file',str(candidate/'.condarc'),'--set','ssl_verify',str(bundle)],'configure private candidate trust',raw=True)
        run(['env','config','vars','set','-p',str(candidate)]+[k+'='+v for k,v in values.items()],'configure private candidate activation',raw=True)
        (root/'candidate-explicit.txt').write_text(run(['list','-p',str(candidate),'--explicit'],'record verified candidate package URLs',runtime=candidate,raw=True))
        summary['conda_update'].update(status='candidate-verified',candidate_version=after['conda']['version'])
        summary['status']='ready-for-review'
    except (Exception,KeyboardInterrupt) as exc:
        summary['status']={'solving':'solve-failed','installing':'install-failed','verifying':'verification-failed'}.get(summary['status'],'preparation-failed')
        summary['issues'].append(str(exc));say('Candidate incomplete: '+str(exc));log.write(traceback.format_exc())
        try:after=records(candidate) if candidate.is_dir() else {}
        except (OSError,ValueError) as record_error:summary['issues'].append('Cannot inventory partial candidate: '+str(record_error))
    finally:
        try:
            try:
                if baseline is not None:
                    summary['source_state_after']=stage_source_state(base)
                    summary['source_metadata_unchanged']=summary['source_state_after']==baseline
                    if not summary['source_metadata_unchanged']:
                        summary['status']='source-changed';summary['issues'].append('Source metadata changed during staging; comparison is stale. No promotion performed.')
                if source_digest is not None:
                    summary['source_ca_unchanged']=hashlib.sha256(source.read_bytes()).hexdigest()==source_digest
                    if not summary['source_ca_unchanged']:
                        summary['status']='source-changed';summary['issues'].append('Source CA changed during staging; review the trust source.')
            except (OSError,ValueError) as exc:
                summary['status']='source-check-failed';summary['issues'].append('Cannot verify source metadata after staging: '+str(exc))
            summary['finished_at']=datetime.datetime.now(datetime.timezone.utc).isoformat()
            write_stage_report(root,summary,before,after)
            say('Candidate status: '+summary['status'])
            say('Review: '+str(root/'review.md'))
            say('Package comparison: '+str(root/'comparison.csv'))
            say('Shared base promotion performed: NO')
        finally:log.close();os.umask(old_umask)
    return 0 if summary['status']=='ready-for-review' else 2


USER_TRUST_AUDIT = AUDIT.replace('print(json.dumps(d))', '''
d['ssl_paths'] = ssl.get_default_verify_paths()._asdict()
import hashlib
d['default_ca_fingerprints'] = [hashlib.sha256(c).hexdigest().upper()
    for c in ssl.create_default_context().get_ca_certs(binary_form=True)]
print(json.dumps(d))
''')

CURL_PROBE_SETUP = r'''
import json, os, pathlib, re, shutil, subprocess, sys
def curl_probe(prefix, require_selected=False):
    prefix=pathlib.Path(prefix).resolve();binary=prefix/'bin/curl'
    if not binary.is_file():raise RuntimeError('Missing Conda curl executable; libcurl alone does not supply bin/curl: '+str(binary))
    meta={}
    for path in (prefix/'conda-meta').glob('*.json'):
        record=json.loads(path.read_text())
        if record.get('name') in ('curl','libcurl'):meta[record['name']]=record
    if set(meta)!={'curl','libcurl'}:raise RuntimeError('Both Conda curl and libcurl records are required')
    result=subprocess.run([str(binary),'-q','--version'],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
    if result.returncode:raise RuntimeError('Conda curl cannot start: '+result.stderr.strip())
    first=result.stdout.splitlines()[0] if result.stdout else ''
    match=re.search(r'^curl (\S+).*\blibcurl/(\S+)',first)
    if not match or match.group(1)!=meta['curl']['version'] or match.group(2)!=meta['libcurl']['version']:
        raise RuntimeError('curl executable/loaded libcurl does not match installed records: '+first)
    if meta['curl']['version']!=meta['libcurl']['version']:raise RuntimeError('curl/libcurl package versions do not match')
    selected=shutil.which('curl')
    if require_selected and (not selected or pathlib.Path(selected).resolve()!=binary.resolve()):
        raise RuntimeError('PATH selects '+str(selected)+' instead of '+str(binary)+'. Reload the intended module or activate its base, then clear the shell command cache (hash -r).')
    return {'executable':str(binary),'selected_on_path':selected,'version':match.group(1),'loaded_libcurl':match.group(2),'startup':first}
'''
CURL_PROBE = CURL_PROBE_SETUP+"\nprint(json.dumps(curl_probe(pathlib.Path(sys.prefix), 'selected' in sys.argv[1:])))\n"
CURL_HTTPS_PROBE = CURL_PROBE_SETUP+r'''
from urllib.parse import urlsplit
url=sys.argv[1]
if urlsplit(url).scheme!='https':raise RuntimeError('curl HTTPS probe requires an HTTPS package source')
info=curl_probe(pathlib.Path(sys.prefix),True)
result=subprocess.run([info['executable'],'-q','--no-insecure','--fail','--head','--location',
    '--proto','=https','--proto-redir','=https','--connect-timeout','15','--max-time','30',
    '--output',os.devnull,'--write-out','%{http_code}',url],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=40)
if result.returncode:raise RuntimeError('Conda curl HTTPS request failed: '+result.stderr.strip())
print(json.dumps({'url':url,'http_status':result.stdout.strip(),'curl':info}))
'''

USER_IMPORT_PROBE = CURL_PROBE_SETUP+r'''
import sys, json, pathlib, zlib, click, packaging, cse_user_probe
assert pathlib.Path(sys.prefix).resolve() == pathlib.Path(sys.argv[1]).resolve()
assert cse_user_probe.answer() == 42
assert zlib.decompress(zlib.compress(b'CSE')) == b'CSE'
print(json.dumps({'prefix':sys.prefix,'python':sys.version,'click':click.__file__,
                 'packaging':packaging.__file__,'local_build':cse_user_probe.__file__,
                 'curl':curl_probe(pathlib.Path(sys.prefix), True)}))
'''


def verification_source_url(value):
    parsed=urlsplit(value)
    if parsed.scheme!='https' or not parsed.hostname:
        raise RuntimeError('User download verification requires HTTPS package sources')
    if 'emudhra' in parsed.hostname.lower() or parsed.hostname.lower().endswith('we-have-a-problem.com'):
        raise RuntimeError('Incident test-site connections are forbidden; use local offline chains')


def redact_verification(text):
    def clean(match):
        try:
            p=urlsplit(match.group(0));host=p.hostname or ''
            if p.port:host+=':'+str(p.port)
            path=re.sub(r'/t/[^/]+','/t/<REDACTED>',p.path)
            return urlunsplit((p.scheme,host,path,'<REDACTED>' if p.query else '', ''))
        except ValueError:return '<REDACTED URL>'
    return re.sub(r'https?://[^\s\"\'<>]+',clean,text)


def check_user_trust(prefix, config, env, audit, pip_config):
    setting=config.get('ssl_verify',True)
    if setting is False or str(setting).lower() in ('false','0','no'):
        raise RuntimeError('Conda certificate verification is disabled')
    if str(env.get('CONDA_SSL_VERIFY','')).lower() in ('false','0','no') or env.get('PYTHONHTTPSVERIFY')=='0':
        raise RuntimeError('Certificate verification is disabled by the current environment')
    paths=set(native_bundle_paths(prefix))
    paths.update(Path(value).expanduser() for value in audit.get('bundles',{}).values() if value)
    if isinstance(setting,str) and setting.lower() not in ('true','truststore'):
        paths.add(Path(os.path.expandvars(setting)).expanduser())
    for key in ('CONDA_SSL_VERIFY','REQUESTS_CA_BUNDLE','CURL_CA_BUNDLE','SSL_CERT_FILE','PIP_CERT'):
        value=env.get(key)
        if value and value.lower() not in ('true','false','truststore','1','0'):
            paths.add(Path(os.path.expandvars(value)).expanduser())
    for key,value in pip_config.items():
        if key.endswith('.trusted-host') and value:
            raise RuntimeError('pip trusted-host bypasses normal TLS verification; remove it before this check')
        if key.endswith(('.index-url','.extra-index-url')) and value:
            for url in str(value).split():verification_source_url(url)
        if key.endswith('.cert') and value:paths.add(Path(value).expanduser())
        if (key.endswith(('.target','.prefix','.root','.log')) and value) or (key.endswith('.user') and str(value).lower() in ('1','true','yes')):
            raise RuntimeError('pip destination/user/log overrides prevent a private-only verification run')
    if env.get('PIP_TRUSTED_HOST'):raise RuntimeError('pip trusted-host bypasses normal TLS verification')
    if str(env.get('PIP_NO_INDEX','')).lower() in ('1','true','yes'):
        raise RuntimeError('pip is configured offline; this mode must verify a real package download')
    for key in ('PIP_INDEX_URL','PIP_EXTRA_INDEX_URL'):
        for url in env.get(key,'').split():verification_source_url(url)
    if any(env.get(key) for key in ('PIP_TARGET','PIP_PREFIX','PIP_ROOT','PIP_LOG')) or str(env.get('PIP_USER','')).lower() in ('1','true','yes'):
        raise RuntimeError('pip destination/user/log overrides prevent a private-only verification run')
    directories={value for value in (env.get('SSL_CERT_DIR'),audit.get('ssl_paths',{}).get('capath')) if value}
    for value in directories:
        for directory in value.split(os.pathsep):
            if not directory:continue
            folder=Path(directory)
            if not folder.is_dir():raise RuntimeError('Configured CA directory is unavailable: '+str(folder))
            for path in folder.iterdir():
                if path.is_file() and '-----BEGIN CERTIFICATE-----' in path.read_text(errors='replace'):paths.add(path)
    matched=set(audit.get('default_ca_fingerprints',())) & set(ROOTS)
    evidence=[]
    for path in sorted(paths):
        data=path.read_bytes();present=set(dict(pem_entries(data.decode()))) & set(ROOTS)
        matched.update(present)
        evidence.append({'path':str(path),'sha256':hashlib.sha256(data).hexdigest(),'incident_roots':sorted(present)})
    if matched:raise RuntimeError('Known incident roots remain in selected trust: '+', '.join(ROOTS[h] for h in sorted(matched)))
    return evidence


def report_user_verification(directory):
    summary=json.loads((directory/'verification-summary.json').read_text())
    print('SAVED USER VERIFICATION: '+summary['status']+' | base: '+summary['base'])
    for name,result in summary['checks'].items():print('  '+name+': '+result['status'])
    for issue in summary['issues']:print('  ATTENTION: '+issue)
    print('Saved evidence for account '+str(summary['uid'])+'; no checks rerun or files changed.')
    return 0


def verify_user_install(args, base, env):
    root=args.verify_user.expanduser().resolve()
    home=Path.home().resolve()
    if root.exists() or root==home or home not in root.parents or base==root or base in root.parents:
        raise RuntimeError('Choose a new private directory under your home, outside the base installation')
    if any((p/'conda-meta/history').exists() for p in root.parents):
        raise RuntimeError('Choose a new private directory outside existing Conda environments')
    if any(c in str(root) for c in (os.pathsep,',','\n')):raise RuntimeError('Private directory has an unsupported path delimiter')
    original_umask=os.umask(0o077)
    try:root.mkdir(mode=0o700,parents=True,exist_ok=False)
    except BaseException:os.umask(original_umask);raise
    prefix=root/'env';env=dict(env)
    env.update(CONDA_PKGS_DIRS=str(root/'pkgs'),CONDA_ENVS_PATH=str(root/'envs'),CONDA_REGISTER_ENVS='false',
               CONDA_OFFLINE='false',CONDA_DRY_RUN='false',CONDA_AUTO_UPDATE_CONDA='false',
               CONDA_NOTIFY_OUTDATED_CONDA='false',CONDA_NUMBER_CHANNEL_NOTICES='0',CONDA_REPORT_ERRORS='false',
               PYTHONDONTWRITEBYTECODE='1',PYTHONUSERBASE=str(root/'python-user'),PIP_DISABLE_PIP_VERSION_CHECK='1',
               PIP_CACHE_DIR=str(root/'pip-cache'),TMPDIR=str(root/'tmp'),XDG_CACHE_HOME=str(root/'user-cache'))
    for key in ('CSE_CONDA_PERMISSION_HOLDS','CSE_CONDA_APPROVED_PLAN'):env.pop(key,None)
    for name in ('pkgs','envs','pip-cache','tmp','user-cache'):(root/name).mkdir(mode=0o700)
    names=('base-trust','base-curl','base-curl-https','conda-create','private-trust','conda-install','pip-download-install','pip-local-build',
           'activation-imports','private-permissions','base-unchanged','offline-chain-rejection')
    summary={'script_revision':SCRIPT_REVISION,'base':str(base),'prefix':str(prefix),'uid':os.geteuid(),
             'status':'running','checks':{name:{'status':'not-run'} for name in names},'issues':[],
             'limits':['This account and these exercises only; repeat as a representative ordinary user.',
                       'No full application/compiler validation or proxy-upstream trust verification.',
                       'Root fingerprint screening is separate from offline chain-rejection testing.']}
    baseline=None;native_before=None;phase='prepare';command_number=0
    log=(root/'run.log').open('w',buffering=1)
    def say(message):message=redact_verification(message);print(message,flush=True);log.write(message+'\n')
    def run(command, raw=False, allow_failure=False):
        nonlocal command_number
        command=list(map(str,command));command_number+=1
        display=command if '-c' not in command else command[:command.index('-c')]+['-c','<local verification program>']
        say('Check: '+phase)
        finished=threading.Event();started=time.monotonic()
        def progress():
            while not finished.wait(30):say('Still checking %s (%ds elapsed)'%(phase,time.monotonic()-started))
        heartbeat=threading.Thread(target=progress,daemon=True);heartbeat.start()
        timed_out=False
        try:result=subprocess.run(command,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=600)
        except subprocess.TimeoutExpired as exc:
            decode=lambda value:value.decode(errors='replace') if isinstance(value,bytes) else value or ''
            result=subprocess.CompletedProcess(command,None,decode(exc.stdout),decode(exc.stderr));timed_out=True
        finally:finished.set();heartbeat.join()
        (root/('command-%03d.json'%command_number)).write_text(redact_verification(json.dumps({
            'phase':phase,'argv':display,'returncode':result.returncode,'timed_out':timed_out,'stdout':result.stdout,'stderr':result.stderr},indent=2)))
        if timed_out:raise RuntimeError('User verification command timed out after 600 seconds; private work may be partial')
        if result.returncode and not allow_failure:raise RuntimeError(diagnostic_text(result.stdout,result.stderr))
        if allow_failure:return result
        if raw:return result.stdout
        data=json.loads(result.stdout)
        if isinstance(data,dict) and (data.get('success') is False or data.get('dry_run') and '--dry-run' not in command):
            raise RuntimeError('Command did not perform the requested transaction')
        return data
    def conda(values,raw=False):return run([base/'bin/python','-I','-B','-c',LIBMAMBA_CLI]+values,raw=raw)
    def check(name,operation):
        nonlocal phase
        phase=name
        try:
            value=operation();summary['checks'][name]={'status':'passed','evidence':value};return value
        except Exception as exc:
            summary['checks'][name]={'status':'failed','detail':redact_verification(str(exc))};raise
    def pip_config(py):
        settings={}
        for line in run([py,'-I','-B','-m','pip','config','list'],raw=True).splitlines():
            if '=' in line:
                key,value=line.split('=',1)
                try:settings[key]=ast.literal_eval(value)
                except (ValueError,SyntaxError):settings[key]=value
        return settings
    def solve_install(verb,specs):
        common=[verb,'-p',str(prefix),'--solver','libmamba','--json','--no-pin']+channel_args
        if verb=='create':common+=['--copy','--no-default-packages','--no-shortcuts']
        plan=conda(common+specs+['--dry-run']);check_plan(plan,None,{spec_name(value) for value in specs})
        for record in plan.get('actions',{}).get('LINK',[]):
            if record.get('url'):verification_source_url(record['url'])
        final,exact=exact_plan_specs(records(prefix) if prefix.exists() else {},plan,{},args.channel,config)
        conda(common+exact+['--yes'])
        installed=records(prefix);verify_installed_plan(final,installed)
        verify_minimums({name:{} for name in ('pip','certifi','ca-certificates')},installed)
        return {'requested':specs,'installed':sorted(installed)}
    try:
        say('PRIVATE USER VERIFICATION | base: '+str(base)+' | account UID: '+str(os.geteuid()))
        summary['base_access']=[access_snapshot(path) for path in (base,base/'bin',base/'bin/python',base/'bin/conda')]
        before=records(base);baseline=stage_source_state(base,before)
        native_before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in native_bundle_paths(base)}
        config=conda(['config','--show','--json'])
        _,urls,channel_args,_,_,_=environment_channels(before,args.channel,config)
        for url in urls:verification_source_url(url)
        audit=run([base/'bin/python','-I','-B','-c',USER_TRUST_AUDIT])
        trust=check('base-trust',lambda:check_user_trust(base,config,env,audit,pip_config(base/'bin/python')))
        check('base-curl',lambda:run([base/'bin/python','-I','-B','-c',CURL_PROBE,'selected']))
        check('base-curl-https',lambda:run([base/'bin/python','-I','-B','-c',CURL_HTTPS_PROBE,urls[0].rstrip('/')+'/noarch/repodata.json']))
        python_version=before['python']['version'].split('.')
        specs=['python='+'.'.join(python_version[:2]),'pip>='+MINIMUM['pip'],'certifi>='+MINIMUM['certifi'],
               'ca-certificates>='+MINIMUM['ca-certificates'],'setuptools','wheel','curl']
        check('conda-create',lambda:solve_install('create',specs))
        audit=run([prefix/'bin/python','-I','-B','-c',USER_TRUST_AUDIT])
        trust+=check('private-trust',lambda:check_user_trust(prefix,config,env,audit,pip_config(prefix/'bin/python')))
        check('conda-install',lambda:solve_install('install',['click']))
        audit=run([prefix/'bin/python','-I','-B','-c',USER_TRUST_AUDIT])
        trust+=check('private-trust',lambda:check_user_trust(prefix,config,env,audit,pip_config(prefix/'bin/python')))
        py=prefix/'bin/python'
        def pip_download():
            run([py,'-I','-B','-m','pip','install','--no-input','--no-user','--disable-pip-version-check','--no-cache-dir','--no-deps',
                 '--only-binary=:all:','--force-reinstall','--report',root/'pip-install.json','packaging'],raw=True)
            report=json.loads((root/'pip-install.json').read_text())
            if not report.get('install'):raise RuntimeError('pip reported no package download/install')
            for entry in report['install']:verification_source_url(entry['download_info']['url'])
            return {'report':'pip-install.json'}
        check('pip-download-install',pip_download)
        project=root/'local-project';project.mkdir()
        (project/'pyproject.toml').write_text('[build-system]\nrequires = ["setuptools", "wheel"]\nbuild-backend = "setuptools.build_meta"\n')
        (project/'setup.cfg').write_text('[metadata]\nname = cse-user-probe\nversion = 0.0.1\n[options]\npy_modules = cse_user_probe\n')
        (project/'cse_user_probe.py').write_text('def answer():\n    return 42\n')
        wheels=root/'built-wheels';wheels.mkdir()
        def local_build():
            run([py,'-I','-B','-m','pip','wheel','--no-input','--no-index','--no-deps','--no-build-isolation',
                 '--wheel-dir',wheels,project],raw=True)
            run([py,'-I','-B','-m','pip','install','--no-input','--no-user','--no-index','--no-deps','--find-links',wheels,'cse-user-probe'],raw=True)
            run([py,'-I','-B','-m','pip','check'],raw=True)
            return {'project':'local-project','wheels':'built-wheels'}
        check('pip-local-build',local_build)
        shell='set -eu; source "$1"; conda activate "$2"; python -I -B -c "$3" "$2"'
        check('activation-imports',lambda:run(['bash','--noprofile','--norc','-c',shell,'cse-user-verification',
                                              base/'etc/profile.d/conda.sh',prefix,USER_IMPORT_PROBE]))
        def permissions():
            evidence=[]
            for path in (prefix,prefix/'lib',root/'pkgs',wheels):
                probe=path/'.cse-write-probe';renamed=path/'.cse-rename-probe'
                probe.write_text('check');probe.rename(renamed);renamed.unlink()
                evidence.append(access_snapshot(path))
            return evidence
        check('private-permissions',permissions)
        if args.chains_dir:
            def chains():
                openssl=prefix/'bin/openssl' if (prefix/'bin/openssl').is_file() else Path(shutil.which('openssl') or '/usr/bin/openssl')
                for path in dict.fromkeys(row['path'] for row in trust):
                    verify_chains(openssl,Path(path),args.chains_dir.expanduser().resolve(),env,lambda command,allow_failure=False:run(command,allow_failure=allow_failure))
                return {'bundles_checked':len(trust),'network_test_sites_contacted':False}
            check('offline-chain-rejection',chains)
        else:summary['checks']['offline-chain-rejection']={'status':'not-tested','detail':'Supply approved local --chains-dir files for offline rejection tests.'}
        summary['status']='passed'
    except (Exception,KeyboardInterrupt) as exc:
        summary['status']='failed';summary['issues'].append(redact_verification(str(exc)));say('Check failed: '+str(exc))
    finally:
        try:
            def unchanged():
                if baseline is None:raise RuntimeError('No initial source fingerprint was captured')
                if stage_source_state(base)!=baseline or {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in native_bundle_paths(base)}!=native_before:
                    raise RuntimeError('Base metadata, configuration or PEM files changed during verification; review concurrent activity')
                return {'metadata_and_native_pems':'unchanged','shared_package_cache':'not selected for writes'}
            check('base-unchanged',unchanged)
        except Exception as exc:summary['status']='failed';summary['issues'].append(redact_verification(str(exc)))
        try:
            (root/'verification-summary.json').write_text(redact_verification(json.dumps(summary,indent=2)))
            lines=['# Miniforge user verification','', 'Status: '+summary['status'],'','Base: `'+str(base)+'`',
                   '','| Check | Result |','| --- | --- |']
            lines+=['| '+name+' | '+item['status']+' |' for name,item in summary['checks'].items()]
            lines+=['','## Issues']+['- '+issue for issue in summary['issues']]+['','## Coverage limits']+['- '+limit for limit in summary['limits']]
            (root/'verification.md').write_text('\n'.join(lines)+'\n')
            say('User verification: '+summary['status'].upper()+' | report: '+str(root/'verification.md'))
        finally:log.close();os.umask(original_umask)
    return 0 if summary['status']=='passed' else 2


def curl_dependency_scope(meta, plan):
    graph=dict(meta)
    # Some Conda LINK summaries omit dependencies; FETCH records and installed
    # records retain them. Do not erase known dependency edges with a short row.
    for action in ('FETCH','LINK'):
        for record in plan.get('actions',{}).get(action,[]):graph[record['name']]=dict(graph.get(record['name'],{}),**record)
    needed=set();pending=['curl','libcurl']
    while pending:
        name=pending.pop()
        if name in needed:continue
        needed.add(name)
        pending.extend(spec_name(dep) for dep in graph.get(name,{}).get('depends',()))
    return needed


def repair_curl(args, base, env):
    """Target curl and its dependency closure; never repeat the full base update."""
    logdir=(args.log_dir or Path.home()/'.cse-trust-logs'/('curl-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f'))).expanduser().resolve()
    if logdir==base or base in logdir.parents:raise RuntimeError('Repair logs must be outside the base installation')
    logdir.mkdir(mode=0o700,parents=True,exist_ok=False);logdir.chmod(0o700)
    env=dict(env,CONDA_PKGS_DIRS=str(logdir/'pkgs'),CONDA_REGISTER_ENVS='false',CONDA_AUTO_UPDATE_CONDA='false',
             CONDA_NUMBER_CHANNEL_NOTICES='0',PYTHONDONTWRITEBYTECODE='1')
    row={'prefix':str(base),'status':'incomplete','issues':[],'changes_started':False,'phase':'prepare curl repair',
         'curl_repair':{'policy':'curl/libcurl and required dependencies only; existing applications/managers retained'}}
    before={};after={};number=0;lock=None
    with (logdir/'run.log').open('w',buffering=1) as log:
        def say(value):value=redact_verification(value);print(value,flush=True);log.write(value+'\n')
        def runjson(values,program=LIBMAMBA_CLI,process_env=None):
            nonlocal number
            number+=1;command=[str(base/'bin/python'),'-I','-B','-c',program]+list(map(str,values))
            started=time.monotonic();finished=threading.Event()
            def heartbeat():
                while not finished.wait(30):say('Still working: %s (%ds elapsed)'%(row['phase'],time.monotonic()-started))
            worker=threading.Thread(target=heartbeat,daemon=True);worker.start()
            try:result=subprocess.run(command,env=process_env or env,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                      timeout=180 if '--dry-run' in values or 'search' in values else 600)
            finally:finished.set();worker.join()
            (logdir/('command-%03d.json'%number)).write_text(redact_verification(json.dumps({'phase':row['phase'],'argv':list(map(str,values)),
                'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr},indent=2)))
            if result.returncode:raise RuntimeError(diagnostic_text(result.stdout,result.stderr))
            data=json.loads(result.stdout)
            if data.get('success') is False or data.get('dry_run') and '--dry-run' not in values:
                raise RuntimeError('Conda did not perform the requested curl repair transaction')
            return data
        try:
            say('Mode: '+('APPLY' if args.apply else 'CURL REPAIR DRY RUN; package metadata may be refreshed, no base changes'))
            say('Base: '+str(base));say('Private logs: '+str(logdir))
            if args.apply:
                lock=(base/'.cse-curl-maintenance.lock').open('a');fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                if os.fstat(lock.fileno()).st_uid==os.geteuid():
                    os.fchown(lock.fileno(),-1,maintenance_gid());os.fchmod(lock.fileno(),0o664)
            before=records(base);baseline=stage_source_state(base,before)
            config=runjson(['config','--show','--json'])
            package_config={key:value for key,value in config.items() if key!='pinned_packages'}
            # This repair deliberately uses conda-forge (or its configured mirror)
            # for BOTH outputs of the split curl recipe, not a historical system binary.
            _,urls,channel_args=requested_channels(args.channel,package_config)
            if args.offline and not any(url.startswith('file://') for url in urls):
                raise RuntimeError('Offline curl repair uses a fresh private cache; supply --channel file:///approved/mirror with curl and its dependencies')
            source=choose_source(args,config,base);text,_=filtered_bundle([source]+args.extra_ca)
            bundle=logdir/'repair-ca-bundle.pem';bundle.write_text(text)
            empty=logdir/'empty-ca-dir';empty.mkdir()
            env.update({key:str(bundle) for key in ('CONDA_SSL_VERIFY','REQUESTS_CA_BUNDLE','SSL_CERT_FILE','CURL_CA_BUNDLE','PIP_CERT')})
            env.update(SSL_CERT_DIR=str(empty),CONDA_OFFLINE='true' if args.offline else 'false')
            flags=channel_args+(['--offline'] if args.offline else [])
            row['phase']='find newest stable curl available to this installation'
            # search accepts channel selection, not the solver's priority flag.
            available=runjson(['search','--json']+[flag for flag in flags if flag!='--strict-channel-priority']+['curl'])
            versions=[record['version'] for record in available.get('curl',()) if re.fullmatch(r'\d+(?:\.\d+)*',str(record.get('version','')))]
            if not versions:raise RuntimeError('No stable curl release is available in the approved conda-forge sources')
            target=max(versions+[record['version'] for name,record in before.items() if name in ('curl','libcurl')],key=version)
            row['curl_repair'].update(target=target,channels=urls)
            row['phase']='solve targeted curl/libcurl repair'
            common=['install','-p',str(base),'--solver','libmamba','--json','--no-pin']+flags
            plan=runjson(common+['--update-deps','curl>='+target,'libcurl>='+target,'--dry-run'])
            (logdir/'000-plan.json').write_text(json.dumps(plan,indent=2))
            allowed=curl_dependency_scope(before,plan)-{'python','python_abi','conda','conda-libmamba-solver','mamba','libmamba','libmambapy'}
            check_plan(plan,allowed);holds=permission_holds(base,before);verify_permission_holds(plan,holds)
            final,exact=exact_plan_specs(before,plan,{},args.channel,package_config)
            if not all(name in final and version(final[name][0])>=version(target) for name in ('curl','libcurl')):
                raise RuntimeError('The plan does not provide both curl and libcurl at the requested version')
            if final['curl'][0]!=final['libcurl'][0]:raise RuntimeError('The plan mixes curl/libcurl versions')
            if before.get('curl') and not (base/'bin/curl').is_file() and not any(record['name']=='curl' for record in plan.get('actions',{}).get('LINK',())):
                raise RuntimeError('curl metadata exists but its executable is missing; a reviewed curl reinstall is required')
            row['package_plan']=[{'name':record['name'],'before':before.get(record['name'],{}).get('version','absent'),
                'after':record['version'],'build':record.get('build_string') or record.get('build')} for record in plan.get('actions',{}).get('LINK',())]
            say('Target curl/libcurl: '+target+'; planned changes: '+(', '.join(record['name'] for record in row['package_plan']) or 'none'))
            if args.apply:
                if stage_source_state(base)!=baseline:raise RuntimeError('Base changed during repair planning; no transaction attempted')
                (logdir/'000-before-packages.json').write_text(json.dumps(before,indent=2))
                # Guard ALL non-dependency packages against implicit relinks too.
                env['CSE_CONDA_PERMISSION_HOLDS']=json.dumps({'prefix':str(base),'packages':sorted((set(before)-allowed)|set(holds))})
                row['phase']='install validated curl repair';row['changes_started']=True
                runjson(common+exact+['--yes'])
                after=records(base);verify_installed_plan(final,after)
                (logdir/'000-after-packages.json').write_text(json.dumps(after,indent=2));row['package_inventory_verified']=True
                row['package_changes']=[{'name':name,'before':before.get(name,{}).get('version','absent'),'after':record['version']} for name,record in after.items()
                    if name not in before or (record['version'],record['build'])!=(before[name]['version'],before[name]['build'])]
                row['phase']='filter installed native PEM files'
                trust_args=argparse.Namespace(**vars(args));trust_args.log_dir=logdir/'native-trust'
                maintain_native_trust(base,trust_args)
                row['phase']='normalize shared base permissions';row['permissions']={};row['skipped_paths']=[]
                warnings=public_permissions(base,base,True,say,row['skipped_paths'],[base/PATH_BACKUPS],row['permissions'])
                row['phase']='check Conda curl and loaded library in the current module environment'
                # Do not hide the user's loaded libraries or PATH for this check.
                runtime_env=os.environ.copy();runtime_env['PYTHONDONTWRITEBYTECODE']='1'
                row['curl_repair']['runtime']=runjson(['selected'],program=CURL_PROBE,process_env=runtime_env)
                runtime=row['curl_repair']['runtime']
                say('Selected curl: '+str(runtime.get('selected_on_path'))+' | version='+str(runtime.get('version'))+' | loaded libcurl='+str(runtime.get('loaded_libcurl')))
                if not args.offline:
                    source_url=next((url for url in urls if url.startswith('https://')),None)
                    if not source_url:raise RuntimeError('No HTTPS package source available for the curl connectivity check')
                    verification_source_url(source_url)
                    row['phase']='check Conda curl HTTPS access'
                    row['curl_repair']['https']=runjson([source_url.rstrip('/')+'/noarch/repodata.json'],program=CURL_HTTPS_PROBE,process_env=runtime_env)
                else:row['curl_repair']['https']={'status':'not-tested','reason':'offline repair'}
                row['status']='updated-with-skips' if warnings else 'updated'
            else:row['status']='previewed'
        except (Exception,KeyboardInterrupt) as exc:
            row['issues'].append(redact_verification(str(exc)));say('ATTENTION: '+str(exc))
        finally:
            try:
                if row.get('package_inventory_verified'):
                    directory=logdir/'000-user-changes'
                    manifest=write_package_changes(directory,before,after,{'evidence':'verified-installed','coverage':'full inventory',
                        'prefix':str(base),'rollout_status':row['status'],'note':'Targeted curl repair. Review remaining permission, native trust and PATH/runtime checks separately.'})
                    row['package_change_list']={'path':str(directory/'README.md'),'counts':manifest['counts'],'evidence':manifest['evidence']}
                (logdir/'summary.json').write_text(json.dumps([row],indent=2))
                say('Curl repair: '+row['status']+' | logs: '+str(logdir))
                if row['issues']:say('Installed packages may have changed; read this run before retrying or repeating a full rollout.')
            finally:
                if lock:lock.close()
    return 0 if row['status'] in ('previewed','updated','updated-with-skips') else 2


def main():
    ap = argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--version',action='version',version='patch_miniforge_trust.py revision %d'%SCRIPT_REVISION)
    ap.add_argument('--base-guide',action='version',version=BASE_ROLLOUT_GUIDE,help='Print the ordered base-only team rollout guide and exit; no access or network checks')
    ap.add_argument('--export-changes',type=Path,metavar='SAVED_RUN_DIR',help='Export user-facing package changes from saved run/stage records only; no installed software or network access')
    ap.add_argument('--changes-output',type=Path,metavar='NEW_DIR',help='New destination for --export-changes; default SAVED_RUN_DIR/user-changes')
    ap.add_argument('miniforge', nargs='?', type=Path)
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--repair-curl',action='store_true',help='Target only the base curl executable, matched libcurl and necessary dependencies; default dry-run, add --apply to repair')
    ap.add_argument('--verify-user',type=Path,metavar='NEW_HOME_DIR',help='Post-install online user checks in a new private home directory; no base updates or cse membership needed')
    ap.add_argument('--stage',type=Path,metavar='NEW_PRIVATE_DIR',help='Solve and install a fresh private base candidate with comparison reports; source base stays read only; no --apply needed')
    ap.add_argument('--stage-skip',action='append',default=[],metavar='PACKAGE',help='Omit this application request from --stage; repeatable; dependencies may still require it')
    ap.add_argument('--promote',type=Path,metavar='REVIEWED_STAGE_DIR',help='Validate the reviewed exact set against its original base; add --apply to install it in place')
    ap.add_argument('--check-permissions',action='store_true',help='Read-only complete known-path permission preflight with private owner-grouped reports; may combine with --promote to inspect candidate paths')
    ap.add_argument('--inspect-trust',action='store_true',help='Read actual CSE/base CA files and configuration; no updates')
    ap.add_argument('--trust-only',action='store_true',help='Filter existing base Miniforge PEM files in place; no packages, new CA path, or shell snippet')
    scope=ap.add_mutually_exclusive_group()
    scope.add_argument('--base-only',action='store_true',help='Select only the loaded base; update Conda and compatible base packages together')
    scope.add_argument('--only',type=Path,action='append',default=[],help='Select only this exact environment; repeatable; still uses the base conda/CSE bundle')
    scope.add_argument('--all-envs',action='store_true',help='Opt into discovery and maintenance of all eligible environments; default is base only')
    ap.add_argument('--channel',action='append',default=[],help='Additional approved community channel or mirror; repeatable; Anaconda defaults excluded')
    ap.add_argument('--report',type=Path,metavar='LOG_DIR_OR_latest',help='Read an existing summary/run.log and explain failures; no updates, group checks or network')
    ap.add_argument('--diagnose',type=Path,metavar='LOG_DIR_OR_latest',help='Repeat the saved failed solve as a dry run with detailed conflicts and access checks; may refresh repodata')
    ap.add_argument('--diagnostic-timeout',type=int,metavar='SECONDS',help='Time limit for --diagnose; positive seconds (default: 600)')
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
    if args.repair_curl:
        if args.export_changes or args.changes_output or args.verify_user or args.stage or args.stage_skip or args.promote or args.check_permissions or args.report or args.diagnose or args.inspect_trust or args.trust_only or args.only or args.all_envs or args.include or args.exclude or args.scan_root or args.upgrade_conda or args.chains_dir or args.diagnostic_timeout is not None:
            ap.error('--repair-curl is base scoped; combine with --apply, --channel, --offline, source options or --log-dir')
        if os.geteuid()==0:ap.error('Run as the maintenance account, not root')
        maintenance_gid();env=safe_environment();base=find_base(args.miniforge,env)
        if not maintainable(base):raise RuntimeError('No maintenance access to the loaded base')
        return repair_curl(args,base,env)
    if args.changes_output and not args.export_changes:ap.error('--changes-output requires --export-changes')
    if args.export_changes:
        if args.miniforge or args.apply or args.verify_user or args.stage or args.stage_skip or args.promote or args.check_permissions or args.report or args.diagnose or args.inspect_trust or args.trust_only or args.base_only or args.all_envs or args.only or args.include or args.exclude or args.scan_root or args.log_dir or args.upgrade_conda or args.offline or args.ca_bundle or args.extra_ca or args.channel or args.chains_dir or args.diagnostic_timeout is not None:
            ap.error('--export-changes reads saved records only; combine with --changes-output or --verbose')
        return export_package_changes(args.export_changes,args.changes_output)
    if args.verify_user:
        if args.apply or args.stage or args.stage_skip or args.promote or args.check_permissions or args.report or args.diagnose or args.inspect_trust or args.trust_only or args.all_envs or args.only or args.include or args.exclude or args.scan_root or args.log_dir or args.upgrade_conda or args.offline or args.ca_bundle or args.extra_ca or args.diagnostic_timeout is not None:
            ap.error('--verify-user is an online private user check; combine only with source prefix, --channel, --chains-dir or --verbose')
        if os.geteuid()==0:ap.error('Run user verification as an ordinary account, not root')
        env=os.environ.copy();env['PYTHONDONTWRITEBYTECODE']='1'
        return verify_user_install(args,find_base(args.miniforge,env),env)
    if args.trust_only and (args.all_envs or args.only or args.include or args.exclude or args.scan_root or args.channel or args.upgrade_conda or args.chains_dir):
        ap.error('--trust-only maintains the loaded base PEMs only; do not combine it with package, chain-check, or other-environment options')
    if args.stage_skip and not args.stage:ap.error('--stage-skip requires --stage')
    if args.check_permissions and (args.apply or args.stage or args.report or args.diagnose or args.inspect_trust or args.trust_only or args.all_envs or args.only or args.include or args.exclude or args.scan_root or args.channel or args.upgrade_conda or args.chains_dir or args.diagnostic_timeout is not None):
        ap.error('--check-permissions is read only and base scoped; combine only with --promote, --log-dir and source/offline options')
    if args.stage:
        if args.apply or args.promote or args.report or args.diagnose or args.inspect_trust or args.trust_only or args.all_envs or args.only or args.include or args.exclude or args.scan_root or args.log_dir or args.chains_dir or args.upgrade_conda or args.diagnostic_timeout is not None:
            ap.error('--stage cannot be combined with apply/report/diagnose/trust or other-environment modes; logs stay in the new private stage directory')
        if any(not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]*',name) for name in args.stage_skip):ap.error('--stage-skip takes package names only')
        if os.geteuid()==0:ap.error('Run staging as your normal account, not root')
        env=safe_environment();env['PYTHONDONTWRITEBYTECODE']='1'
        return stage_base(args,find_base(args.miniforge,env),env)
    if args.promote and (args.report or args.diagnose or args.inspect_trust or args.trust_only or args.all_envs or args.only or args.include or args.exclude or args.scan_root or args.upgrade_conda or args.channel):
        ap.error('--promote targets only its staged source base and approved channels; do not combine it with other scopes/modes')
    if args.diagnostic_timeout is not None and (not args.diagnose or args.diagnostic_timeout<=0):
        ap.error('--diagnostic-timeout requires --diagnose and a positive number of seconds')
    if (args.include or args.scan_root) and not args.all_envs:
        ap.error('--include and --scan-root require --all-envs; use --only for exact prefixes')
    if args.diagnose:
        if args.apply or args.report or args.inspect_trust or args.trust_only:
            ap.error('--diagnose cannot be combined with apply/report/trust modes')
        return diagnose_existing(args.diagnose,find_base(args.miniforge,safe_environment()),args.offline,
                                 args.diagnostic_timeout if args.diagnostic_timeout is not None else 600)
    if args.report:
        if args.apply or args.inspect_trust or args.trust_only: ap.error('--report cannot be combined with apply/trust modes')
        return report_existing(args.report,args.verbose)
    if args.inspect_trust:
        if args.apply or args.trust_only: ap.error('--inspect-trust cannot be combined with --apply/--trust-only')
        base=find_base(args.miniforge,safe_environment())
        return inspect_trust(base,[p.expanduser().resolve() for p in args.only])
    preflight=None
    if args.promote or args.check_permissions:
        if os.geteuid()==0:ap.error('Run permission preflight as the maintenance account, not root; root access hides user restrictions')
        audit_env=safe_environment();audit_env['PYTHONDONTWRITEBYTECODE']='1'
        audit_base=args.miniforge.expanduser().resolve() if args.miniforge else find_base(None,audit_env)
        preflight=permission_audit(audit_base,args.log_dir,args.promote,([args.ca_bundle] if args.ca_bundle else [])+args.extra_ca)
        if args.check_permissions:return 2 if preflight['summary']['affected_path_count'] else 0
        if preflight['summary']['promotion_blocking_path_count']:
            print('Promotion stopped before base changes; review all reported paths and inspection gaps, then rerun the audit.')
            return 2
    if os.geteuid() == 0: ap.error('Run as the software maintenance account, not root')
    cse_gid = maintenance_gid()  # validate before any deployment changes
    os.umask(0o002)
    env = safe_environment()
    if args.promote:env['PYTHONDONTWRITEBYTECODE']='1'
    base = Path(preflight['summary']['base']) if preflight else find_base(args.miniforge,env); conda = base/'bin/conda'
    if not maintainable(base): raise RuntimeError('No user/group maintenance access to base')
    approved=load_promotion(args.promote,base,holds=preflight['holds']) if args.promote else None
    if approved:
        env.update(CONDA_PKGS_DIRS=str(approved['root']/'pkgs'),CONDA_REGISTER_ENVS='false',CONDA_SHORTCUTS='false',
                   CONDA_NUMBER_CHANNEL_NOTICES='0',CONDA_REPORT_ERRORS='false',CONDA_SAFETY_CHECKS='enabled',
                   CONDA_EXTRA_SAFETY_CHECKS='true',CONDA_ROLLBACK_ENABLED='true')
    if args.trust_only: return maintain_native_trust(base,args)
    config_cmd=[base/'bin/python','-I','-B','-c',LIBMAMBA_CLI,'config','--show','--json'] if approved else [conda,'config','--show','--json']
    config = json.loads(capture(config_cmd,env))
    channel_names,channel_urls,channel_args = requested_channels(args.channel,{k:v for k,v in config.items() if k!='pinned_packages'})
    source = choose_source(args,config,base)
    bundle_text, removed = filtered_bundle([source] + args.extra_ca)
    skipped_paths = []
    if not args.all_envs and not args.only: prefixes=[base]
    elif args.only: prefixes=list(dict.fromkeys(p.expanduser().resolve() for p in args.only))
    else: prefixes=discover(base,conda,env,args.include,args.scan_root,args.exclude,skipped_paths)
    exclusions=[p.expanduser().resolve() for p in args.exclude]
    prefixes=[p for p in prefixes if not any(p==x or x in p.parents for x in exclusions)]
    if not prefixes: raise RuntimeError('No prefixes selected after exclusions')
    logdir = preflight['root'] if preflight else (args.log_dir or Path.home()/'.cse-trust-logs'/datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')).expanduser().resolve()
    if any(logdir == p or p in logdir.parents for p in prefixes):
        raise RuntimeError('Logs must be outside all selected environment trees')
    if not preflight:logdir.mkdir(mode=0o700,parents=True,exist_ok=False)
    os.chmod(str(logdir),0o700)
    log = open(str(logdir/'run.log'),'w',buffering=1)
    def say(s): print(s,flush=True);log.write(s+'\n')
    def detail(s):
        if args.verbose: print(s,flush=True)
        log.write(s+'\n')
    say('Mode: '+('APPLY' if args.apply else 'REVIEWED PROMOTION DRY RUN; no base changes' if approved else 'LOCAL PREVIEW; no network operations'))
    say('Script revision: %d'%SCRIPT_REVISION)
    say('Solver: installed libmamba only; external plugin discovery disabled; base Conda and packages update together.')
    say('Fallback/explicit package channels: '+', '.join(channel_names)+'; Anaconda defaults excluded; external plugins disabled; no PyPI fallback')
    say('Resolved channel URLs: '+', '.join(channel_urls))
    say('Scope: '+', '.join(str(p)+(' [BASE]' if p==base else '') for p in prefixes))
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
        event['access_details']=[access_snapshot(p) for p in denied_paths(stdout+'\n'+stderr+'\n'+diagnostic)]
        (logdir/filename).write_text(json.dumps(dict(event,argv=list(map(str,cmd)),stdout=stdout,stderr=stderr),indent=2))
        row.setdefault('command_failures',[]).append(event)
        for snapshot in event['access_details']:print_access(snapshot,say)
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
            limit=30 if '__cse_solver_probe__' in cmd or XKB_CACHE_PROBE in cmd else (180 if 'search' in cmd or ('install' in cmd and '--dry-run' in cmd) else None)
            invocation=solver_invocation(base,cmd)
            if approved and str(cmd[0])==str(conda):invocation=[str(base/'bin/python'),'-I','-B','-c',LIBMAMBA_CLI]+list(map(str,cmd[1:]))
            elif approved and str(cmd[0])==str(base/'bin/python') and '-I' in cmd and '-B' not in cmd:
                invocation=list(map(str,cmd));invocation.insert(2,'-B')
            r = subprocess.run(invocation,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=limit)
        except subprocess.TimeoutExpired as exc:
            decoded=lambda value: value.decode(errors='replace') if isinstance(value,bytes) else (value or '')
            raise record_failure(cmd,decoded(exc.stdout),decoded(exc.stderr),None,
                                 'Conda planning did not complete within %s seconds; no package transaction attempted. Inspect the saved command output.'%limit) from exc
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
        if not approved:
            atomic_write(bundle,bundle_text)
            atomic_write(trustdir/'use-ca.sh','# Source after loading your CSE module.\n'+''.join('export %s=%s\n'%(k,shlex.quote(v)) for k,v in values.items()))
            env.update(values)
            env['CONDA_OFFLINE'] = 'true' if args.offline else 'false'
    if approved:
        preview_bundle=logdir/'promotion-ca-bundle.pem';preview_bundle.write_text(bundle_text);os.chmod(str(preview_bundle),0o600)
        preview_empty=logdir/'empty-ca-dir';preview_empty.mkdir(mode=0o700)
        env.update({k:str(preview_bundle) for k in ('CONDA_SSL_VERIFY','REQUESTS_CA_BUNDLE','SSL_CERT_FILE','CURL_CA_BUNDLE','PIP_CERT')})
        env['SSL_CERT_DIR']=str(preview_empty);env['CONDA_OFFLINE']='true' if args.offline else 'false'
    certificate_status={'status':'pending verified promotion' if approved and args.apply else 'written' if args.apply else 'planned','bundle':str(bundle),'source':str(source),'roots_selected_for_removal':removed,
                        'sha256':hashlib.sha256(bundle.read_bytes()).hexdigest() if args.apply and not approved else None,
                        'activation':'shell snippet available; each application/environment must use it; OS/proxy unchanged'}
    (logdir/'certificate-status.json').write_text(json.dumps(certificate_status,indent=2))
    say('CSE certificate stage: '+certificate_status['status'].upper()+' | '+str(bundle))
    if approved:say('Promotion uses a private CA copy for planning/downloads; shared trust is configured only after the reviewed packages verify.')
    else:say('Certificate preparation reads the source into one shared CSE copy. Only selected prefixes receive package/configuration updates; their package-owned PEMs may be replaced by conda.')
    if certificate_status['sha256']: say('CSE bundle SHA256: '+certificate_status['sha256'])
    for i,prefix in enumerate(prefixes):
        row = {'prefix':str(prefix),'status':'incomplete','issues':[],'skipped_paths':[],'changes_started':False,'ownership':path_owner(prefix)};results.append(row)
        if preflight:row['permission_preflight']={key:preflight['summary'][key] for key in ('report_directory','affected_path_count','repair_target_count','inspection_gap_count')}
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
            broad = prefix == base
            package_config={k:v for k,v in config.items() if k!='pinned_packages'} if broad else config
            row['installed_channels']=sorted({str(r.get('channel') or r.get('url') or 'unknown') for r in meta.values()})
            channel_names,channel_urls,channel_args,origins,excluded_origins,unknown_origins=environment_channels(meta,args.channel,package_config)
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
                if not broad and pinfile.is_file():
                    for pin in pinfile.read_text().splitlines():
                        pin=pin.split('#',1)[0].strip()
                        if '::' in pin and not allowed_pin_origin(pin.split('::',1)[0],channel_names,channel_urls,config):
                            raise RuntimeError('Channel-qualified prefix pin outside requested channels: '+pin)
            upgrade_conda = args.upgrade_conda or broad
            row['package_policy']='base applications retained; all package pins ignored; dependencies solved together and unused dependencies pruned' if broad else 'targeted maintenance; application packages pinned'
            if approved:row['package_policy']='promote the reviewed exact package set; versions/builds/checksums locked; packages absent from the candidate removed'
            say('Package policy: '+row['package_policy'])
            holds={}
            if broad:
                row['phase']='inspect installed package path access'
                holds=preflight['holds'] if preflight else permission_holds(prefix,meta)
                row['permission_holds']=list(holds.values())
                (logdir/'base-permission-holds.json').write_text(json.dumps(row['permission_holds'],indent=2))
                for hold in holds.values():
                    say('Deferred package: %s=%s=%s | %s | %s'%(hold['name'],hold['version'],hold['build'],hold['path'],hold['reason']))
                env['CSE_CONDA_PERMISSION_HOLDS']=json.dumps({'prefix':str(prefix.resolve()),'packages':sorted(holds)})
                row['conda_update']=conda_update_status(meta)
                row['base_intent']=base_package_intent(meta,prefix,config,ignore_pins=True,held=holds)
                row['package_pin_policy']='ignore stored package pins; apply temporary exact holds only for access-blocked packages'
                row['ignored_pins']=row['base_intent']['ignored_pins']
                say('Base package pins ignored: '+(', '.join(row['ignored_pins']) or 'none configured'))
                (logdir/'base-package-intent.json').write_text(json.dumps(row['base_intent'],indent=2))
                say('Base inventory: %d installed; %d retained application/security requests; %d solver-managed dependencies'%(
                    len(meta),len(row['base_intent']['roots']),len(row['base_intent']['dependencies'])))
                for migration in row['base_intent']['replacements']:
                    say('Base package replacement: '+migration['name']+' -> '+', '.join(migration['replacements']))
                say('Conda update: '+row['conda_update']['status']+
                    ' | current='+str(row['conda_update']['before'])+' | minimum='+CONDA_MINIMUM)
                if approved:
                    row['base_intent'].update(roots=sorted(approved['packages']),dependencies=[])
                    row['promotion']={'stage':str(approved['root']),'manifest_sha256':approved['manifest_sha256'],
                                      'status':'preflight','package_count':len(approved['packages'])}
                    row['reviewed_security_versions']=approved['security_verification']
                    row['conda_update'].update(target=approved['packages']['conda']['version'],
                        reviewed_latest_available=approved['summary'].get('conda_update',{}).get('latest_available'),
                        source=recorded_origin(approved['packages']['conda']),
                        policy='Reviewed candidate target; no new version search')
                    guard={'prefix':str(base),'packages':approved['identity'],
                           'before':{n:[r['version'],r['build']] for n,r in meta.items()}}
                    guard_file=logdir/'approved-promotion-plan.json';guard_file.write_text(json.dumps(guard,indent=2));os.chmod(str(guard_file),0o600)
                    env['CSE_CONDA_APPROVED_PLAN']=str(guard_file)
                    _,channel_urls,channel_args,origins,excluded_origins,unknown_origins=environment_channels(approved['packages'],[],package_config)
                    if excluded_origins or unknown_origins:raise RuntimeError('Reviewed package origins are not usable on this system')
                    row['requested_channels']=channel_urls
                    say('Reviewed package-set SHA256: '+approved['manifest_sha256'])
            else:env.pop('CSE_CONDA_PERMISSION_HOLDS',None)
            retained=set(row['base_intent']['roots']) if broad else None
            targets,allowed,specs = plan_specs(meta,upgrade_conda,broad=broad,roots=retained)
            if broad and not approved:
                specs,row['permission_python_constraint']=permission_hold_specs(meta,specs,holds)
            if approved:specs=qualify_specs([n+'='+r['version']+'='+r['build'] for n,r in sorted(approved['packages'].items())],origins)
            specs=specs if broad else qualify_specs(specs,origins)
            row['package_targets'] = [{'name':n,'current':meta.get(n,{}).get('version','absent'),'request':('>='+MINIMUM[n] if n in MINIMUM else ('>='+CONDA_MINIMUM if n == 'conda' else 'compatible build')),'source':('approved channels in priority order' if broad else origins.get(n,'fallback/explicit allowed channels'))} for n in sorted(targets)]
            if approved:
                for target in row['package_targets']:
                    r=approved['packages'][target['name']];target.update(request='='+r['version']+'='+r['build'],source=origins[target['name']])
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
            if args.apply or approved:
                if row['issues']: raise RuntimeError('Package review required; no package/configuration/permission changes attempted for this prefix')
                row['phase'] = 'save configuration and conda package inventory'
                for relative in ('.condarc','conda-meta/state','conda-meta/history','conda-meta/pinned'):
                    p=prefix/relative
                    if p.is_file(): (logdir/('%03d-before-'%i+relative.replace('/','_'))).write_bytes(p.read_bytes())
                (logdir/('%03d-before-packages.json'%i)).write_text(json.dumps(initial_meta,indent=2))
                (logdir/('%03d-before-explicit.txt'%i)).write_text(run([conda,'list','-p',prefix,'--explicit']).stdout)
                row['phase']='load installed libmamba solver'
                probe=runjson([conda,'__cse_solver_probe__'])
                if probe.get('solver')!='libmamba':raise RuntimeError('Installed libmamba solver could not be loaded; no package update attempted')
                row['solver']='libmamba'
                if approved:
                    info=runjson([conda,'info','--json'])
                    platforms={r['subdir'] for r in approved['packages'].values()}-{'noarch'}
                    if platforms and platforms!={info.get('subdir') or info.get('platform')}:
                        raise RuntimeError('Reviewed package platform differs from this system; stage this system separately')
                if broad and not approved:
                    conda_minimum=select_conda_target(base,meta,origins,config,args.offline,runjson,logdir,row,say)
                    targets,allowed,specs=plan_specs(meta,upgrade_conda,broad=True,conda_minimum=conda_minimum,roots=retained)
                    specs,row['permission_python_constraint']=permission_hold_specs(meta,specs,holds,conda_minimum)
                    if row['permission_python_constraint']:say('Python constraint for deferred packages: '+row['permission_python_constraint'])
                if targets:
                    row['phase'] = 'solve package update (dry run)'
                    cmd=[conda,'install','-p',prefix,'--solver','libmamba','--json']+(['--update-all','--prune','--no-pin'] if broad else ['--freeze-installed'])+channel_args+specs
                    if args.offline: cmd.append('--offline')
                    plan=runjson(cmd+['--dry-run'])
                    (logdir/('%03d-plan.json'%i)).write_text(json.dumps(plan,indent=2))
                    changed=check_plan(plan,allowed,retained)
                    verify_permission_holds(plan,holds)
                    row['package_plan'] = [{'name':r['name'],'before':meta.get(r['name'],{}).get('version','absent'),'after':r['version'],'build':r.get('build_string') or r.get('build')} for r in plan.get('actions',{}).get('LINK',[])]
                    row['package_removals']=planned_removals(plan,row.get('base_intent',{}).get('replacements',[]))
                    for removal in row['package_removals']:
                        say('Validated package removal: %s=%s | %s'%(removal['name'],removal['before'],removal['reason']))
                    detail('Validated package changes: '+(', '.join(changed) or 'none'))
                    # Lock the planned final versions/builds before the execution solve.
                    final,exact=exact_plan_specs(meta,plan,origins,args.channel,package_config)
                    if broad:
                        verify_retained(final,retained)
                        retired={r['name'] for r in row['base_intent']['replacements']} & set(final)
                        if retired:raise RuntimeError('Solver retained superseded package names: '+', '.join(sorted(retired)))
                    if broad:row['conda_update']['plan_conda_version']=final.get('conda',(None,None))[0]
                    verify_minimums(meta,{n:{'version':v} for n,(v,b) in final.items()},upgrade_conda,
                                    row.get('conda_update',{}).get('target',CONDA_MINIMUM))
                    if approved:
                        verify_installed_plan({n:(r['version'],r['build']) for n,r in approved['packages'].items()},
                                              {n:{'version':v,'build':b} for n,(v,b) in final.items()})
                        row['promotion']['status']='validated'
                        if not args.apply:
                            row['conda_update']['status']='reviewed-plan-validated'
                            row['status']='previewed';row['trust_configuration']='would configure after verified package promotion'
                            say('Reviewed promotion dry run passed; no base package/configuration/permission changes made.')
                            continue
                    execution=[conda,'install','-p',prefix,'--solver','libmamba','--json','--yes']+(['--prune','--no-pin'] if broad else ['--freeze-installed'])+channel_args+exact
                    if args.offline: execution.append('--offline')
                    migration=None
                    xkb=next((r for r in plan.get('actions',{}).get('LINK',[]) if r['name']=='xkeyboard-config'),None)
                    xkb_path=prefix/XKB_PATH
                    if broad and xkb and xkb_path.is_dir() and not xkb_path.is_symlink():
                        row['phase']='inspect planned XKB layout'
                        probe_cmd=[base/'bin/python','-I','-B','-c',XKB_CACHE_PROBE,json.dumps(xkb)]
                        payload=runjson(probe_cmd)
                        if not payload.get('available'):
                            row['phase']='download validated packages for XKB layout preflight (no transaction)'
                            # Older Conda reports successful cache preparation as
                            # CondaExitZero JSON on stderr, with no stdout JSON.
                            run(execution+['--download-only'])
                            payload=runjson(probe_cmd)
                        if not payload.get('available'):raise RuntimeError('Planned XKB package payload is unavailable for layout preflight')
                        if payload.get('target') is not None:
                            if payload['target']!=XKB_LINK:raise RuntimeError('Unsupported XKB symlink target: '+str(payload['target']))
                            inspect_xkb_tree(prefix,meta)  # Refuse custom/shared data before changing anything.
                            migration={'planned_package':{'name':'xkeyboard-config','version':xkb['version'],'build':xkb.get('build_string') or xkb.get('build')}}
                            row['xkb_migration']=migration
                    row['changes_started']=True
                    try:
                        if migration is not None:
                            row['phase']='preserve old XKB directory before symlink migration'
                            preserve_xkb_tree(prefix,meta,migration)
                            say('Original XKB directory preserved: '+migration['backup'])
                            say('XKB recovery manifest: '+migration['manifest'])
                        row['phase'] = 'install validated package plan'
                        runjson(execution)
                    except Exception:
                        if migration is not None:
                            try:restore_xkb_tree(prefix,meta,migration)
                            except Exception as recovery_error:
                                migration.update(status='recovery-needed',reason=str(recovery_error))
                                row['issues'].append('XKB recovery required: '+str(recovery_error))
                                try:save_xkb_manifest(migration)
                                except (OSError,KeyError):pass
                            say('XKB migration after failure: '+migration.get('status','not moved')+' | '+migration.get('manifest','no backup created'))
                        raise
                row['phase'] = 'verify installed package versions'
                after_meta=records(prefix)
                row['package_changes'] = [{'name':n,'before':initial_meta.get(n,{}).get('version','absent'),'after':r['version']} for n,r in sorted(after_meta.items()) if n not in initial_meta or (r['version'],r['build']) != (initial_meta[n]['version'],initial_meta[n]['build'])]
                if broad:row['conda_update']['installed_conda_version']=after_meta.get('conda',{}).get('version')
                row['security_verification']=verify_minimums(meta,after_meta,upgrade_conda,
                                                           row.get('conda_update',{}).get('target',CONDA_MINIMUM))
                if targets:verify_installed_plan(final,after_meta)
                if approved:
                    differences=promotion_differences(after_meta,approved['packages'])
                    if differences:raise RuntimeError('Installed packages differ from reviewed checksums/platforms: '+', '.join(differences))
                    if runjson([conda,'__cse_solver_probe__']).get('solver')!='libmamba':raise RuntimeError('Promoted Conda/solver startup failed')
                    row['promotion']['status']='packages-verified'
                if row.get('xkb_migration'):verify_xkb_tree(prefix,row['xkb_migration'])
                if broad:row['curl_runtime']=runjson([py,'-I','-B','-c',CURL_PROBE])
                (logdir/('%03d-after-packages.json'%i)).write_text(json.dumps(after_meta,indent=2))
                row['package_inventory_verified']=True
                for removal in row.get('package_removals',[]):removal['status']='verified'
                if broad:row['conda_update'].update(status='updated',after=after_meta.get('conda',{}).get('version'))
                row['phase'] = 'configure prefix trust'
                row['changes_started']=True
                if approved:
                    atomic_write(bundle,bundle_text)
                    atomic_write(trustdir/'use-ca.sh','# Source after loading your CSE module.\n'+''.join('export %s=%s\n'%(k,shlex.quote(v)) for k,v in values.items()))
                    env.update(values)
                    certificate_status.update(status='written',sha256=hashlib.sha256(bundle.read_bytes()).hexdigest())
                    (logdir/'certificate-status.json').write_text(json.dumps(certificate_status,indent=2))
                run([conda,'config','--file',prefix/'.condarc','--set','ssl_verify',bundle])
                run([conda,'env','config','vars','set','-p',prefix]+[k+'='+v for k,v in values.items()])
                row['trust_configuration'] = 'configured to use'
                row['phase'] = 'verify runtime packages and trust bundles'
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
            permissions = public_permissions(prefix,base,args.apply,detail,row['skipped_paths'],
                                             args.exclude+[base/PATH_BACKUPS]+sorted({Path(p['blocking_path']) for p in hold_paths(holds)}),row['permissions'])
            skipped_paths.extend(row['skipped_paths'])
            row['permission_warnings'] = permissions
            row['status']='incomplete' if row['issues'] else (('updated' if args.apply else 'previewed') + ('-with-skips' if permissions or holds else ''))
            if approved and row['status'].startswith('updated'):row['promotion']['status']='completed'
        except (PermissionError,FileNotFoundError) as exc:
            row['status']='incomplete' if row['changes_started'] else 'skipped'
            row['issues'].append(str(exc))
            if exc.filename: row['access_details']=[access_snapshot(exc.filename)]
            skipped_paths.append({'path':str(exc.filename or prefix),'stage':'environment','reason':str(exc),'prefix':str(prefix)})
            log.write(traceback.format_exc())
        except Exception as exc:
            row['issues'].append(str(exc));log.write(traceback.format_exc())
        if args.apply and row['issues'] and row.get('conda_update',{}).get('status')!='updated' and 'conda_update' in row:
            row['conda_update']['status']='incomplete'
        if row.get('package_inventory_verified'):
            try:
                change_dir=logdir/('%03d-user-changes'%i)
                manifest=write_package_changes(change_dir,initial_meta,after_meta,{
                    'evidence':'verified-installed','coverage':'full inventory','prefix':str(prefix),'rollout_status':row['status'],
                    'note':'Recorded before/after installed Conda inventories. Review the separate rollout, certificate and user-operation results before declaring the installation ready.'})
                row['package_change_list']={'path':str(change_dir/'README.md'),'evidence':manifest['evidence'],'counts':manifest['counts']}
            except Exception as exc:
                row['status']='incomplete';row['issues'].append('User change-list generation failed: '+str(exc))
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
    if args.apply and (not approved or certificate_status['status']=='written'):
        say('For the current shell after loading your module: . '+shlex.quote(str(trustdir/'use-ca.sh')))
    say('No external test endpoints were contacted. OS/proxy trust unchanged.')
    log.close()
    if lockfile:lockfile.close()
    return 2 if any(r['status'] == 'incomplete' for r in results) else 0


if __name__=='__main__':
    try:sys.exit(main())
    except (Exception,KeyboardInterrupt) as exc:
        print('STOPPED: '+str(exc),file=sys.stderr);sys.exit(2)
