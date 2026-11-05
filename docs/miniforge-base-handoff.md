# Update the loaded Miniforge base

Use this folder's updated `patch_miniforge_trust.py` and `README.md` (revision 40+).
Load the intended site/compiler and Miniforge module. Run with Python 3.8+ as the
maintenance account (`cse` group), not root. The existing Miniforge installation
and other environments are kept; no preliminary package update is required.

**1. Review/approve the plan.**

```bash
python3 patch_miniforge_trust.py --promote
```

The script finds the loaded base, chooses a new private review directory, runs
the necessary preparation/access checks, and shows the remaining package changes.
An already updated base keeps installed versions/builds and adds missing matched
curl/dependencies. It does not need an old stage directory or a base rebuild.
For an initial/security refresh, any needed private staging runs automatically.
Review the output and require **Review READY** before continuing.

**2. Apply that review.**

```bash
python3 patch_miniforge_trust.py --promote --apply
```

It automatically finds the saved review for this installation. Apply installs
only the reviewed package set, merges OS CAs into native Miniforge PEMs through
the incident certificate/key filter, and normalizes eligible base/link permissions.
RHEL and SUSE certificate paths are detected locally. Known eMudhra incident
certificates/keys are filtered before writing; OS trust files stay unchanged.
Read the final status and any owner/access review notes.

Reviews default to `~/.cse-trust-reviews/`, separated by host and installation.
Each review/apply gets a new directory; existing records are preserved. Optional
`--log-dir PATH` chooses a location; an existing path gets a new suffixed sibling.
If the base or CA sources changed after review, rerun step 1, then step 2.
Use the normal maintenance window/recovery arrangements and stop concurrent base
updates/jobs before applying. Repeat for each distinct GCC/Intel installation.

**User check in the SCSC environment (after apply).**

Open a fresh shell, load the same normal site/compiler and Miniforge modules
that users load, and run from this script's folder. Prefer a representative
ordinary user account; the maintenance account can also run this check. It does
not need shared write access or change base permissions.

```bash
cse_check="$HOME/cse-user-check-$(date +%Y%m%d-%H%M%S)-$$"
python3 patch_miniforge_trust.py --verify-user "$cse_check"
python3 patch_miniforge_trust.py --report "$cse_check"
```

The test directory must be new; keep it and its reports if anything fails. This
checks curl HTTPS access, Conda creation/install in a private environment, pip
HTTPS download/install and a small wheel build, activation/imports, and private
write/rename/delete access. Test packages and caches stay under that private
directory. It does not update base packages, rewrite base certificates or change
shared permissions. It also audits base files (including Jedi/Typeshed stubs), ownership, modes and
file metadata before/after. Unexpected changes fail `base-unchanged`; inspect
`base-file-changes.json`. Other environment/package-cache trees are excluded
from that file walk; the test uses its own private caches. Package downloads/environment creation can take a few minutes.

Require **User verification: PASSED** in the output. In `verification.md`,
require the `base-unchanged` row to show `passed`. The report covers the account and operations tested; repeat
with an ordinary user to check their actual access. No live incident sites are
contacted. Other checks/repairs remain optional when troubleshooting.

**One-time repair for older Miniforge permissions (or whenever needed).** Load the affected
Miniforge setup and run as the account that owns the affected files. Confirm the
printed `Base` path matches that installation before applying:

```bash
python3 patch_miniforge_trust.py --version  # require revision 40 or newer
python3 patch_miniforge_trust.py --permissions-only
python3 patch_miniforge_trust.py --permissions-only --apply
```

Revision 40 sweeps the **entire selected Miniforge tree**, including `envs/`,
`pkgs/` and older nested Conda environments. It repairs group/modes throughout
without package transactions or certificate-content changes. Already compliant
paths are skipped; hardlinks contained within the tree are updated once in place.
Credential/config files and keys also receive `cse` group read/write access:
files 0660, directories 2770, executables 0770, with no access for other users.
Public Python directories named `credentials`, `tokens` or `secrets` (including
Jedi/Typeshed Docker stubs) use ordinary shared modes: files 0664, directories
2775, executables 0775. Recovery backups and directory-link targets remain
protected and listed. Owner/access/ACL/filesystem exceptions are reported explicitly.
It keeps owner UIDs: a maintainer's owner name can
remain while group `cse` has shared access. Other owners' files/ACL exceptions need
their owner/admin; review the printed skip report. Changing the owner account
itself is a separate owner/admin action. No `--promote` rerun is needed for this.

**Pip install fails in the post-build user check.** Read its existing report
first; no rebuild or reinstall is needed to inspect the saved failure:

```bash
python3 patch_miniforge_trust.py --report "$cse_check"
```

Use the test directory printed earlier if `cse_check` is no longer set. Revision
38 shows the failed pip command, exit status and actual saved error. Give Ravon
that error and the failed check name; it distinguishes certificate/download,
package/build and Python/launcher failures without guessing.

**Additional startup checks for a PATH-selected Miniforge (no module required).**
If pip itself will not start, keep the failing setup selected and collect these
read-only checks in a new private directory. They install nothing and make no
shared permission changes:

```bash
cse_pip_check="$(mktemp -d "$HOME/cse-pip-check.XXXXXX")"
(
  cd "$cse_pip_check" || exit 1
  export PYTHONDONTWRITEBYTECODE=1 PIP_DISABLE_PIP_VERSION_CHECK=1
  type -a conda python python3 pip pip3
  conda info --base
  python -B -c 'import sys; print("Python:", sys.executable); print("Prefix:", sys.prefix)'
  python -B -m pip --version
  python -I -B -m pip --version
  pip --version
) > "$cse_pip_check/startup.txt" 2>&1
printf 'Pip startup report: %s\n' "$cse_pip_check/startup.txt"
```

If `python -m pip` works but `pip` fails, focus on the selected launcher/PATH and
its interpreter. If only `python -I -m pip` works, check `PYTHONPATH`/user-site
interference. If both fail, send Ravon the exact error from `startup.txt`; the
installer's age alone does not identify a repair. If startup succeeds but a
package download/install fails, run the private user check above and send its
failed check/report. Keep these reports private; do not reinstall or upgrade
shared packages merely to make this diagnostic pass.

`--approve` is an alias for `--promote`. The two maintenance commands above stay
the same; the user check is a separate validation after applying.
For the detailed base guide, **contact Ravon directly**. If a step fails, give
Ravon the failing command and printed review/test/log directory.
Keep those records. The promotion log's `000-user-changes/README.md` and CSV/JSON
files provide the user-facing package change list; private logs are not for publication.
