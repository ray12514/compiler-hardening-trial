# Update the loaded Miniforge base

Use this folder's updated `patch_miniforge_trust.py` and `README.md` (revision 36+).
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
shared permissions. It also checks that base metadata/configuration/PEMs stayed
unchanged. Package downloads/environment creation can take a few minutes.

Require **User verification: PASSED** in the output. In `verification.md`,
require the `base-unchanged` row to show `passed`. The report covers the account and operations tested; repeat
with an ordinary user to check their actual access. No live incident sites are
contacted. Other checks/repairs remain optional when troubleshooting.

`--approve` is an alias for `--promote`. The two maintenance commands above stay
the same; the user check is a separate validation after applying.
For the detailed base guide, **contact Ravon directly**. If a step fails, give
Ravon the failing command and printed review/test/log directory.
Keep those records. The promotion log's `000-user-changes/README.md` and CSV/JSON
files provide the user-facing package change list; private logs are not for publication.
