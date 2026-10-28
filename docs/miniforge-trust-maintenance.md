# CSE Miniforge trust maintenance

The maintenance script is [scripts/patch_miniforge_trust.py](../scripts/patch_miniforge_trust.py).
It updates selected shared conda environments and builds a CSE-managed, incident-filtered
CA bundle from your existing site PEM. It leaves the OS and the inspection proxy unchanged.
No external incident test endpoint is contacted.

## Update Conda and base packages in the existing installation

Revision 23 keeps the installed Miniforge distribution, prefix, module selection
and Spack version pin. Miniforge `24.11.2-1` does not itself require a reinstall
for an in-place Conda/base package update. No installer is downloaded or rerun.
The default scope is **the loaded base only**. Other environments require an
explicit `--only PATH` or `--all-envs` selection.

Load the usual Miniforge module and run:

```bash
python3 patch_miniforge_trust.py --base-only
python3 patch_miniforge_trust.py --base-only --apply
```

`python3 patch_miniforge_trust.py --version` should print revision 23. Each run
also records its revision so an older copied script can be identified directly.

Use `--ca-bundle /path/to/CSE-existing-bundle.pem` when a particular existing site
bundle is required. The source is read to prepare the managed CSE copy before
package retrieval. The update then:

1. Loads the installation's bundled **libmamba** solver. External plugin
   entry-point discovery is blocked; only the installed solver hook is enabled.
   `conda-pypi` and other external hooks are not enabled.
2. Checks the approved source's current repodata for the newest stable Conda,
   retaining the security floor `26.9.4` and any newer installed version.
3. Identifies the retained base requests from explicit installation history and
   the installed dependency graph. Installer/full-package maintenance snapshots
   do not turn every old dependency into a permanent application requirement.
   Standalone packages and dependency cycles are retained conservatively.
   Python, Conda, the solver and installed security targets are retained as
   unversioned requests or required security minimums. Access-blocked packages
   instead receive temporary exact holds, with a Python series constraint where
   needed to prevent their relinking.
4. Solves **one full base update** with `--update-all --prune --no-pin`. Stored base
   package pins are ignored, including `conda-meta/pinned`, `pinned_packages`
   configuration and environment settings. Python, Mamba,
   NumPy, Jupyter, Boost and their dependencies can move together. Base requests
   use approved channel priority rather than historical per-package channel locks.
   Dependencies can be replaced or removed when the updated retained packages no
   longer need them. Retained applications cannot silently disappear.
5. Rejects excluded Anaconda defaults sources, missing retained applications and
   unmet security minimums, then installs the validated final versions/builds and
   removals. Installed records must match that complete plan.
6. Verifies the installed records before configuring prefix trust and inspecting
   runtime bundles and shared permissions.

The process-local solver wrapper explicitly forwards pruning through Conda's
transaction API: Conda 24.11 accepts the install CLI flag but does not forward it.
Retired names do not get update jobs; the solver explicitly removes those names
in the same transaction, so they cannot hold their replacements to older versions.
Both libmamba 1.x and 2.x request APIs are supported. No installed solver files are patched.
For local/site channels, the validated plan's `base_url` takes priority over its
short display label. The wrapper also preserves file-channel URLs through legacy
Conda MatchSpec parsing/formatting, so the exact execution solve does not turn a
local directory basename into an unrelated public channel. These adjustments are
process-local and do not change stored channel configuration.

There is no preliminary manager-only bootstrap and no classic conflict-hint graph
in this path. A missing/broken installed solver fails before package updates with
its import/startup error. Read-only planning is limited to 180 seconds (the solver
probe to 30 seconds). That planning limit does not interrupt an installation
transaction. Existing `--offline` behavior is preserved.

Non-base prefixes retain their exact Python/application pins and source-qualified
requests. Base package contents change within the existing installation; its
Miniforge module/Spack release label does not change. Keep the maintenance records
with the installation because the original Spack DAG hash does not describe those
updated package contents.

Preview remains local-only and does not load a solver, contact channels or install
packages. `--trust-only` still prepares only the managed trust files. Successful
prefixes print the shell snippet to source after loading the module.

Private logs include `base-package-intent.json` (retained requests, dependencies,
pins and known replacements), `base-conda-search.json`, `NNN-plan.json`, command output and
`conda_update` in `summary.json`, including the original, planned and installed
Conda versions. Removals and their reasons are printed and saved in
`package_removals`. Reports still read legacy `conda_bootstrap` records from older runs.
An install that returns a dry-run result or leaves old installed versions is
reported as incomplete. Apply overrides inherited dry-run settings.

### Obsolete names and unused dependencies

Current [conda-forge Boost recipes](https://github.com/conda-forge/boost-feedstock/blob/main/recipe/meta.yaml)
explicitly prohibit co-installing the old `boost`/`boost-cpp` names with their new
`libboost*` counterparts. For installed conda-forge packages, maintenance maps
`boost` to `libboost-python-devel` and `boost-cpp` to `libboost-devel`, preserving
headers, libraries and development metadata. Old base package pins do not block
this migration. Other package sources are not assumed to share this migration.

An unsatisfiable request or an old version number does not establish that a
package is deprecated. Unknown application conflicts still fail with the solver's
explanation. Ordinary dependencies may disappear only as part of the compatible
retained-package solve, and their removals are recorded as no longer needed,
not as a claim that upstream deprecated them. Availability and ABI compatibility
come from channel metadata for the actual host; the script does not guess that
every package can move to its individually newest release.

### XKB directory-to-symlink migration

New `xkeyboard-config` packages expose `share/X11/xkb` as the relative symlink
`../xkeyboard-config-2`. Older installations have a directory at that path.
A failed cleanup of that directory can surface as `FileExistsError` while Conda
tries to create the symlink. This is a filesystem/linking failure. Conda supports
updating its own package in place; replacing the Miniforge installer is not required.

Revision 21 handles this specific migration in the selected base. It checks the
planned package's extracted payload for the expected symlink. If that payload
is not cached, a `--download-only` stage prepares the validated packages without
executing a package transaction. Older Conda can report successful cache preparation
as `CondaExitZero` on stderr; the exit status and a subsequent payload check determine
whether preparation succeeded.

Before installation, the updater validates the old directory against installed
`xkeyboard-config` file records, then moves it intact to a private directory under
`BASE/share/X11/.cse-trust-path-backups/xkb-*/xkb`. This same-parent-tree rename
preserves file contents, owners, groups and modes. It also keeps `share/X11`
nonempty so Conda's rollback cleanup cannot remove the containing directory.
The private backup is excluded from recursive permission normalization. A manifest
records the source, backup, original inode/ownership and migration state before
data moves. Existing file-conflict checks remain enabled.

Custom/untracked files, other-package files, special files, symlinked parents or
a symlinked replacement-data root stop the migration before the source is moved.
Write/traverse access to the containing `share/X11` directory is required; the
old package files do not need to be chmodded or recursively deleted. A failed
package installation restores the old tree when Conda's package records roll back
and the destination can be restored safely. Partial rollback or unexpected active
contents retain the backup and report `recovery-needed` with its manifest path.
This is a backup of the XKB tree, not a complete environment rollback facility.

Successful installs verify the new symlink and keyboard data. `summary.json` and
`--report` show `xkb_migration`, its status and recovery paths. Diagnostic dry runs
do not perform this migration. The normal base update command needs no extra flag.

### An update is rejected

Use the current script's normal base update first; do not repeat the older
classic-solver diagnostic for longer and longer periods. Libmamba returns a direct
dependency conflict instead of building the classic hint graph. Revision 20
ignores every package pin in the selected base during both planning and exact-plan
installation. For example, `certifi==2024.12.14` cannot hold certifi below the
required `2026.10.19` minimum, and a Python/application pin cannot hold that package
to its old version. This is the normal base behavior; no additional flag is needed.

Ignored pin specs are printed and saved in `ignored_pins` and the base package
inventory. The original prefix pin file is backed up privately. Stored pin files
and shared/user configuration are retained, so ordinary Conda commands outside
this script still use their stored settings. The module/Spack Miniforge release
selection remains unchanged. A package-version pin is separate from a PEM file.
Non-base environments retain their existing targeted maintenance and pin policy.

If a base run still reports a configured-pin conflict, first verify the current revision
and that `--no-pin` appears on both saved install commands. Actual dependency,
platform and channel compatibility requirements remain enforced.

The deprecated `.*` version-spec warning alone is not a conflicting-package finding.
The strict-priority note alone also does not identify the blocker. Actual package
and source choices still come from the validated solve.

Read an existing run without retrying an installation:

```bash
python3 patch_miniforge_trust.py --report latest
```

To repeat a saved failed request as a diagnostic dry run:

```bash
python3 patch_miniforge_trust.py --diagnose latest
```

The diagnostic uses the installed libmamba solver even for a saved classic-solver
command. It preserves the saved package requests, pin policy, strict priority
and managed TLS bundle, strips `--yes`, forces `--dry-run`, prints access snapshots,
and saves private `solver-diagnostic-*.json` output. No package transaction,
trust/configuration update, chmod or chgrp runs. Repodata cache refreshes remain
possible. `--diagnostic-timeout SECONDS` is retained, but extending a classic hint
analysis is no longer the recommended workflow. A saved preview has no failed
package command; select the actual failed apply log directory if needed.

### Shared group access versus ownership

The exact group name required by the maintenance script is `cse`. Effective group
write and traversal access to the affected directories, writable package metadata
and usable caches can permit package replacement without owning every file.
ACLs, sticky directories, file modes and mount policy can still block particular
operations. Initial prefix checks do not prove every later write will succeed.

Changing modes/groups on foreign-owned files is a separate owner/admin operation;
normalization reports those paths as skips. An unsatisfiable package solve is not
by itself evidence of an ownership problem. A write failure should name a denied
or not-writable path and is reported separately. The diagnostic prints your
UID/groups and current effective access to the prefix, `conda-meta`, `.condarc`
and the actual package caches without changing their permissions.

## Retrieve just the script over SSH

Use your usual GitHub SSH key and configuration. This retrieves a shallow Git repository
with file contents fetched on demand, then extracts only the script into your working
directory. Repository files are not checked out. Run from a directory where you want the script:

```bash
(
  set -e
  cse_fetch_dir="$(mktemp -d)"
  trap 'rm -rf -- "$cse_fetch_dir"' EXIT

  git clone --depth 1 --single-branch --branch main \
    --filter=blob:none --no-checkout \
    git@github.com:ray12514/compiler-hardening-trial.git \
    "$cse_fetch_dir/repo"

  git -C "$cse_fetch_dir/repo" show HEAD:scripts/patch_miniforge_trust.py \
    > ./patch_miniforge_trust.py

  git -C "$cse_fetch_dir/repo" rev-parse HEAD \
    > ./patch_miniforge_trust.commit
)
```

The temporary Git checkout is removed; the script and its source commit record remain.
For older Git versions without partial-clone support, omit `--filter=blob:none`.
That transfers more repository data but still extracts just the script.

If you already have this repository cloned, extract the local checkout's version:

```bash
git -C /path/to/compiler-hardening-trial show HEAD:scripts/patch_miniforge_trust.py \
  > ./patch_miniforge_trust.py
```

### Reproduce the earlier revision 12 exactly

The script was updated at commit `3cfb223ceb8ca59a128523627df0d187a75bc9a0`.
That historical revision uses classic solving rather than the current single
libmamba base transaction. Use the current `main` retrieval for revision 23.
For a reproducible download, use the SSH clone block above and add this command
immediately before its `git show` command:

```bash
git -C "$cse_fetch_dir/repo" fetch --depth 1 origin \
  3cfb223ceb8ca59a128523627df0d187a75bc9a0
```

Then replace `HEAD:scripts/patch_miniforge_trust.py` with
`FETCH_HEAD:scripts/patch_miniforge_trust.py` in `git show`, and use
`rev-parse FETCH_HEAD` for the provenance record. Verify this exact script revision:

```bash
echo '7d87e5f2e621368af92d90e288e477c0bb592d85e961390c3bab545ad9964edb  patch_miniforge_trust.py' |
  sha256sum --check
```

### Transfer from your workstation to the HPC login node

If GitHub SSH access is available only on your workstation, retrieve the script there
and copy it using your normal HPC SSH destination:

```bash
scp ./patch_miniforge_trust.py YOUR_USER@YOUR_LOGIN_HOST:./patch_miniforge_trust.py
```

Replace the destination with your actual SSH hostname or configured alias.
Use your established SSH configuration for authentication, ports and jump hosts.

## First establish the certificate state

Package-update failure does not establish whether the CSE bundle was written. In older
revisions, the shared CSE trust files were written before the environment loop. The
message listing roots to remove was computed from the source; it was not a receipt
that applications had switched bundles.

After retrieving this revision, load the intended Miniforge module and run:

```bash
python3 patch_miniforge_trust.py --inspect-trust
```

Or name the installation explicitly:

```bash
python3 patch_miniforge_trust.py /actual/path/to/miniforge --inspect-trust
```

This is read-only and uses no external TLS connections. With an explicit installation
path, it does not execute conda or the environment's Python. It reports:

- Whether the actual managed `etc/cse-trust/ca-bundle.pem` exists and parses.
- Its SHA256 and presence/absence of the four known incident-root fingerprints.
- Base CA package versions relative to this script's minimums.
- Base `ssl/cert.pem`, `ssl/cacert.pem`, and discoverable Python certifi/pip bundles.
- Raw prefix `ssl_verify` settings, activation CA variables, and current-shell CA variables.

Add `--only /path/to/environment` to inspect that prefix alongside the base. An absent
prefix setting does not rule out inherited/user configuration. No known-root match is
screening, not full chain verification. The command returns 0 if the managed bundle is
parseable with those four roots absent; otherwise 2. That return code does not certify
other bundles, application activation, organizational CA completeness, or the proxy.

### Prepare the CSE bundle independently of package updates

If the managed copy is absent or needs rebuilding, explicitly select your approved
existing CSE PEM source. Start with a preview:

```bash
python3 patch_miniforge_trust.py /actual/path/to/miniforge \
  --trust-only --ca-bundle /actual/path/to/CSE-existing-bundle.pem
```

Then apply that stage alone:

```bash
python3 patch_miniforge_trust.py /actual/path/to/miniforge \
  --trust-only --ca-bundle /actual/path/to/CSE-existing-bundle.pem --apply
```

This writes the filtered CSE copy, the managed marker/lock, the dedicated empty CA
lookup directory and `use-ca.sh`. It does not invoke conda, install packages, configure
individual environments, or recursively normalize environment permissions. Your account
still needs maintenance access to the installation and membership in `cse`. The source
PEM is retained; organizational roots are kept except any exact incident-root match.
It remains interim broad-root filtering, not a fresh public CA collection.

`certificate-status.json` records `planned` or `written`, the source, destination and
written bundle SHA256. Normal apply also saves this status before package work, and
prints the certificate stage separately at the end. A startup failure before that
record is written requires checking the actual files with `--inspect-trust`.

The new bundle takes effect for the current shell only when you source the printed
`use-ca.sh` after loading your module, or implement the equivalent module settings.
An application may still use its own trust configuration. This stage does not replace
outdated CA packages, pip's embedded bundles, system trust, or proxy upstream policy.

## Startup error: expected a URL, got auth/location/name fields

Revision 10 incorrectly required `channel_alias` and `custom_channels` values from
`conda config --show --json` to be URL strings. Conda can instead return serialized
Channel objects containing `scheme`, `location`, `name`, `auth`, `token`, `platform`
and `package_filename`. A blank `name` is valid for a channel alias: the requested
channel name is appended to that base. For example, an alias object with
`scheme=https`, `location=conda.anaconda.org` and a blank name resolves conda-forge to
`https://conda.anaconda.org/conda-forge`. It is not a malformed installed package source.

Revision 11 accepts both URL strings and structured Channel objects. Structured custom
channels already include their names, so the resolver does not append the name twice.
Mirror paths and supplied auth/token fields are retained. Structured multichannel
members are also supported. Known Anaconda defaults repositories remain excluded.
This is a script compatibility correction; it does not require editing a working
`.condarc`. That specific startup exception occurs before certificate/package writes
in the failed invocation, although earlier runs may already have written CSE trust files.

Retrieve revision 11 and repeat your previous base-only preview. The published regression
suite (`scripts/test_channel_regressions.py`) covers the reported blank-name alias
object, raw/resolved configuration equivalence, custom channels, mirror paths, labels,
multichannels, source exclusions and simulated preview/apply with structured config.
These local tests do not establish access to repositories from your HPC system.

## HTTP 404 with a blank channel name

`conda.anaconda.org` is the normal public host for conda-forge. The channel root is
`https://conda.anaconda.org/conda-forge`; the bare host is not a named public channel.
A channel object showing `auth=None` does not itself indicate an authentication error.
A blank channel name plus a host-only URL can explain an invalid-channel 404.

Revision 9 could admit a host-only installed channel record, and could strip a real
channel name when a malformed `subdir` field matched that name. Revision 10 rejects
host-only public origins and strips only recognized platform names. For an unusable
channel field, it attempts recovery from the recorded package archive URL. Structured
channel metadata retains its location and name together. If neither source is usable,
the malformed source is not passed to conda; the permitted fallback/explicit channels
remain available. Explicit malformed channels or alias/custom mappings fail locally
with an actionable error instead of generating a repository request.

After retrieving the fixed script, inspect the base scope first:

```bash
python3 patch_miniforge_trust.py /actual/path/to/miniforge \
  --base-only --ca-bundle /actual/path/to/CSE-existing-bundle.pem
```

The preview is local-only. Check `Environment channels from installed records:` and
`Channels used:`; for a conda-forge-only base the list should contain the full
`https://conda.anaconda.org/conda-forge` URL (or your configured site mirror equivalent).
Add `--apply` to attempt the validated solve/update after reviewing that preview.
A preview does not test repository availability. Valid, fully named historical channels
can still return 404 if they were removed, made private, or changed on the mirror;
that requires the exact failing URL and cannot be inferred from a host-only error.

Each new package run saves `NNN-channel-records.json` with the package name, original
channel/URL/subdir, normalized origin and selected origin. Missing/unusable source counts
and this report path are printed without `--verbose`. This makes the metadata behind
a constructed channel visible without searching through a traceback. No `.condarc`
files are automatically rewritten to repair this error. Do not remove the normal
hosting domain or add Anaconda `defaults` in response to the generic conda message.

## Full updates are permitted in the base environment

Revision 20 updates Conda and the compatible Miniforge base in one libmamba
transaction, retaining the full base package-update scope. It no
longer rejects changes to `krb5`, NumPy, matplotlib, matplotlib-base, Python or other
base packages as unrelated. The base solve uses `--update-all --prune --no-pin`
with all package pins ignored. Installed incident-related packages retain
explicit minimum constraints, and installed conda is targeted at >=26.9.4 automatically.
Conda resolves compatible versions using the permitted channels and package dependencies;
this does not promise every package will reach the newest version on every channel.

Use the same base-only command to isolate this work:

```bash
python3 patch_miniforge_trust.py /actual/path/to/miniforge \
  --base-only --ca-bundle /actual/path/to/CSE-existing-bundle.pem --apply
```

The validated solver plan is saved, then executed with exact final versions/builds.
New dependencies and updates to any base package are permitted. The Anaconda defaults
source exclusion, installed-source selection, dependency solving and retained-application
checks remain in force; unused dependencies and superseded names may leave. No `--no-deps` or `--clobber`
bypass is used. Base updates can include major Python/application version changes.

Before executing the plan, all originally installed incident-related conda packages
must remain present at or above the script's minimums. The script repeats that check
against installed records afterward, including conda's requested minimum. The final
summary prints `Verified required minimums`, and `summary.json` stores the actual
versions and minimums in `security_verification`. An unmet or missing required package
is incomplete, even if other base packages updated. Runtime embedded-bundle and startup
checks still apply separately. This verifies package minimums, not proxy protection.

Non-base environments retain the narrower maintenance policy and exact application/
Python pins. `--upgrade-conda` enables conda updates in those prefixes. The existing
mixed pip/uv ownership review also remains; a full conda solve does not authorize
silently overwriting non-conda tools. Preview remains local-only and lists requests;
apply performs the solve and records exact changes.

## Work on the base, then one environment

The base is the default scope and is labeled `[BASE]` in progress output.
You can make that scope explicit with `--base-only`:

```bash
python3 patch_miniforge_trust.py /actual/path/to/miniforge \
  --base-only --ca-bundle /actual/path/to/CSE-existing-bundle.pem
```

Add `--apply` after reviewing that preview. Then select one environment exactly:

```bash
python3 patch_miniforge_trust.py /actual/path/to/miniforge \
  --only /actual/path/to/environment \
  --ca-bundle /actual/path/to/CSE-existing-bundle.pem
```

`--only` is repeatable and replaces discovery; it does not implicitly update base
packages. Apply still uses the base conda executable and writes the shared CSE trust
files. `--base-only` and `--only` cannot be combined. Exclusions still apply. Package
updates remain serial; these flags reduce scope rather than change concurrency.

A failed update does not establish that an environment is unused. The script never
deletes environments on failure. Review obsolete environments separately with their
owners and consumers before explicit retirement; the base must not be retired this way.

## Preview before applying

Load your usual CSE Miniforge module. The script requires Python 3.8+ and the exact
lowercase group `cse`, resolved through the host's group database. Your current login
must include membership in that group. Run as your maintenance account, not root.

Specify your existing CSE PEM explicitly, particularly where it contains the
organizational CA required for the inspection proxy:

```bash
python3 patch_miniforge_trust.py \
  --ca-bundle /actual/path/to/CSE-existing-bundle.pem
```

Without a positional path, the script finds the installation through `CONDA_EXE`
or `conda` on `PATH`. To choose the installation explicitly:

```bash
python3 patch_miniforge_trust.py /actual/path/to/miniforge \
  --ca-bundle /actual/path/to/CSE-existing-bundle.pem
```

Preview performs local discovery, CA parsing and permission inspection. It does not
download packages or run the solver. Review the base path, CA source, selected prefixes,
permission-change counts and reported issues. Default console output omits per-path
permission details. Add `--verbose` to display them; full details are always saved in
the private `run.log`. The end-of-run summary always shows each environment, package
requests (current version and requested minimum), permission counts, trust configuration
and reasons for incomplete work. Preview requests are not solver-confirmed upgrades.
Apply records the validated solver plan and verified installed package changes separately.

## Explain an existing failed run without retrying

Retrieve the updated script, then run:

```bash
python3 patch_miniforge_trust.py --report latest
```

This reads the latest directory containing `summary.json` under your home directory's
`~/.cse-trust-logs`. Check the printed saved run mode: the latest run might be a
preview. To select a particular apply run, use the exact `Private logs:` directory
printed by that run:

```bash
python3 patch_miniforge_trust.py --report "$HOME/.cse-trust-logs/REPLACE_WITH_RUN_DIRECTORY"
```

Replace the last directory component with the actual timestamp directory. Neither
command updates packages, changes certificates or permissions, checks group membership,
nor runs network/subprocess commands. Report mode returns 0 when it successfully
reads the report, regardless of the saved update statuses. `--report --apply` is rejected.

The report shows failed/skipped environments, owners where recorded, saved reasons,
command diagnostics, categories and suggested next steps. It suppresses ordinary
successful rows unless `--verbose` is supplied. For older logs, the command associated
with a generic failure is inferred from the preceding logged command; its return code
was not recorded. JSON errors and exception messages are extracted where available.
This recovery is best-effort: a missing underlying error is reported as unresolved,
not guessed. New runs save `failed-command-NNN.json` with the actual arguments, return
code (null if the executable could not start), operation phase, stdout and stderr;
these details are also referenced in `summary.json`.

The report is plain text; save a copy if needed:

```bash
python3 patch_miniforge_trust.py --report latest > miniforge-failure-report.txt
```

Review paths and command output for credentials or sensitive site details before
sharing outside your authorized team. No reports are sent automatically.

`updated-with-skips` means package/configuration work completed with permission/access
exceptions. It is not counted as a failed package update. `incomplete` can mean the
script deliberately declined an unsupported operation, not just that conda failed.

### Mixed pip/uv and conda ownership

The presence of pip-installed applications alone does not trigger the migration block.
The script blocks a prefix when its audit finds an outdated tool in the security
minimum list without a corresponding conda package record. It reports that tool by
name (for example, `certifi`). New audits also record installer metadata and installation
location when available; these are evidence, not proof of the environment's full history.
A mixed-package review is checked before prefix backup/export/solve commands, so an
unrelated export failure cannot obscure the deliberate block.

Do not bulk uninstall pip/uv tools or force conda to overwrite their files. Conda cannot
fully account for pip's changes. A reviewed migration or replacement environment must
preserve the applications' requirements and use explicitly approved community sources; the
script does not switch to PyPI. The new report identifies these environments separately
from repository/solver failures, so the two problems can be addressed independently.

### Permission denied despite owning the environment

The denied path might be a package cache, a parent, a configuration file or an executable
rather than the environment root. ACLs, missing traversal/execute permissions and
filesystem policy can deny an operation despite apparent ownership. Use the exact path
and command in the report to determine the required repair. New command failures
extract the denied filename when available and attach a snapshot of owner/group,
mode, read/write/execute access, ACL presence and inaccessible ancestors. A snapshot
cannot prove mount/SELinux/server policy or diagnose a race after the fact. Old reports
can recover a filename and take a current snapshot where the legacy log contains it;
a missing path cannot be reconstructed reliably. Snapshots are evidence at their
capture time, not permission repairs. The script does not fix
this by recursively widening unrelated directories or changing another user's owner UID.

### Permission denied on `bin/__pycache__/android_deploy.cpython-*.pyc`

A `.pyc` file is generated Python bytecode; `android_deploy` is an application tool,
not a Conda bootstrap requirement. Its source package can still be part of the
validated base update. Conda may need to rename or remove the old cache while
replacing package files, so an access failure can stop the entire transaction even
when nobody is using that tool. The filename alone does not establish that its
source package is deprecated or safe to remove from the environment.

Check the exact denied path and its containing `bin/__pycache__` directory. On
Unix, renaming/removing a file normally needs write and traversal access to that
directory, plus traversal through ancestors. A foreign-owned `755` directory is
not group writable; `700` also denies other group members traversal. A `755` file
alone does not establish that removal is blocked. Sticky bits, ACLs, read-only
mounts and filesystem policy may impose additional restrictions. Group membership
does not let you chmod or chgrp another user's files.

Have the owner/admin repair the specific shared directory access if that is the
blocker, using the site's group or ACL policy. For a directory intended for the
script's shared policy, that is group `cse`, mode `2775`; ordinary cache files use
`0664`. These are owner/admin changes on foreign-owned paths, not an instruction
to recursively change the prefix or its parents. Removing one disposable cache
file may clear one obstruction but leaves a non-writable directory broken.

Revision 22 captures the containing directory's owner/group, mode, effective
access, ACL presence and sticky bit alongside the denied filename. It prints this
snapshot when a command fails and saves it in the failed-command JSON. Read the
saved report without rerunning an update or solver:

```bash
python3 patch_miniforge_trust.py --report latest
```

For older failed-command logs, the report can take a current snapshot when the
denied path was not already recorded, including CondaMultiError's tuple format.
Existing snapshots remain evidence from the time they were captured. A final
permissions-stage `SKIP PATH` / `updated-with-skips` is nonfatal; an install-phase
`PermissionError` / `incomplete` is a failed package update. Revision 22 improves
this diagnosis; it does not grant missing site access or skip transaction files.

### Update the accessible base packages while deferring blocked packages

Revision 23 does this by default in the selected base. It checks installed package
manifests for paths that the current account cannot replace and keeps each affected
package at its exact installed version and build. It also checks expected Python
caches derived from package-owned `.py` sources, including unrecorded import caches.
It does not guess a package owner from the `android_deploy` name alone. A
foreign-owned file in a writable, traversable directory is not held just because
the UID differs; directory access and sticky restrictions matter.

The remaining base applications and dependencies are solved together for updates.
When a held package has Python files, Python stays within its installed major/minor
series so an interpreter change cannot force that package's noarch relink; Python
patch updates remain possible. Other dependency constraints are solved normally.
Before any native transaction, the restricted solver rejects every unlink or link
of a held package, including a same-build reinstall. It checks the execution solve
as well as the initial dry run. No individual transaction file is silently skipped.
The reported blocked directories are excluded from permission normalization too.

These are temporary constraints for the current run. Existing site/package pins
are still ignored for the base solve, and no pin file or module/Spack selection is
changed. Access is checked again on the next run; after the owner/admin fixes it,
the package can update normally. Non-base environments keep their existing policy.

The script still requires the selected newest stable Conda target and the security
minimums for installed certificate and maintenance packages. If a blocked package
is below its required minimum, or retaining it conflicts with those targets, the
run stops before installation and reports the hold and solver error. It does not
lower a security target to manufacture success. A preflight cannot prove server
policy, immutable flags, future access or every new package path; an unexpected
transaction failure remains a failure and is not retried around a partial update.

Use the normal command after refreshing the script from `main`:

```bash
python3 patch_miniforge_trust.py --version  # revision 23
python3 patch_miniforge_trust.py --base-only --apply
```

A compatible update with held packages reports `updated-with-skips`, verifies the
installed package plan and required minimums, and lists each **Deferred package**,
installed version/build, blocked path and reason. `base-permission-holds.json` also
contains access snapshots. This means the allowed update completed while those
packages remained at their listed versions; it does not mean every base package
was upgraded or that the held packages are patched. The admin can repair the
deferred paths separately.

## Apply

Use your normal snapshot and maintenance-window process. The script saves private
configuration/history records, but does not create a filesystem or package snapshot.

```bash
python3 patch_miniforge_trust.py /actual/path/to/miniforge \
  --ca-bundle /actual/path/to/CSE-existing-bundle.pem \
  --apply
```

Conda remains the package manager. Anaconda `defaults` repositories are a separate
package source and remain excluded.

For each selected environment, the script now reads its installed conda package
records (`conda-meta/*.json`) and automatically reuses their identifiable non-default
channels. Recorded channel fields are preferred, with package URLs as a fallback.
Platform directories and archive filenames are removed from URLs while mirror hosts
and channel label paths are retained. Named channels use the site's current alias
and custom-channel mappings. Sources from one environment do not carry over to another.

In non-base prefixes, where a package's source is identifiable and permitted, its requested spec is qualified
with that channel, for example `https://conda.anaconda.org/bioconda::PACKAGE>=VERSION`.
The base instead uses approved channel priority for compatible builds, without
locking each request to its historical origin. The final execution specs also retain identifiable solver-selected sources. If that
source lacks a compatible fixed build, the update is reported incomplete. The script
does not bypass dependency checks or switch the package's source to force success.

Conda-forge remains an available fallback for dependencies and packages without an
identifiable source. Unknown metadata, development records and PyPI/wheel origins are
not guessed as conda channels. Additional channels can still be supplied explicitly
with repeatable `--channel` when needed:

```bash
python3 patch_miniforge_trust.py /actual/path/to/miniforge \
  --only /actual/path/to/environment --channel bioconda \
  --ca-bundle /actual/path/to/CSE-existing-bundle.pem
```

You do not need `--channel bioconda` if bioconda is already recorded in that environment.
The preview/progress and final summary show selected channel URLs, target package
sources and excluded Anaconda/default origins. `summary.json` records
`package_origins`, `requested_channels`, `excluded_installed_sources` and
`unknown_package_origins` for each prefix.

All install/solve commands use `--override-channels` and strict channel priority.
Unrelated channels from configuration are not silently adopted. Known Anaconda default
URLs and aliases resolving to them are excluded even if recorded in installed packages.
A misleading channel label does not override a known default-repository archive URL.
In non-base prefixes, defaults-qualified pins still block the prefix instead of causing
default downloads; other channel-qualified pins must resolve into that environment's
selected source set. Base updates ignore all package pins, including their channel
constraints. Solver LINK/FETCH records referencing known Anaconda
defaults locations are rejected before executing the install.

An excluded historical source is reported; it is not a claim that the source was
contacted by this run. An unknown private mirror's upstream contents cannot be inferred
from its URL alone. This automatic reuse assumes the recorded non-default sources
were permitted for these existing environments; site source controls still apply.
There is no PyPI or pip-install fallback. Solver subprocesses block external plugin
discovery and explicitly enable only the installed libmamba solver hook.
For disconnected operation, add `--offline`; the necessary packages from the requested approved channels must
already be cached or available through the site mirror mapping.
Outdated pip-managed tools are reported for reviewed migration, without overwriting
pip-owned files automatically.

The base permits a full compatible package update, including conda >=26.9.4.
Other prefixes retain conda by default; add `--upgrade-conda` there to request that
minimum. Non-base Python and scientific packages keep their installed versions/builds.
Blocked dependency plans and unmet security minimums remain incomplete.

## Environment scope

Only base is selected by default. `--only PATH` selects exactly the named prefixes.
With `--all-envs`, base and registered environments are discovered, as are direct children
of the installation's `envs` directory. Eligibility requires actual maintenance access
through your UID or current groups. Registration alone is not ownership.

With `--all-envs`, add an unregistered environment with `--include /path/to/environment`.
Find environments under a known software directory with `--scan-root /path/to/shared/environments`.
`--include` and `--scan-root` require `--all-envs` to avoid silently expanding a narrow scope.
Keep private environments out with `--exclude /path/to/private/environment`;
its descendants are also excluded. These options are repeatable.

All eligible selected prefixes are treated as shared. Run once per distinct installation,
on the relevant system. The script does not discover or log in to remote machines.

## Inaccessible and colleague-owned test directories

An inaccessible environment or child directory does not abort the rest of the run.
Discovery handles access failures per candidate. Permission traversal handles failures
per file/subtree and continues with available siblings. The script does not change
permissions to gain access to an unreadable directory. A leading dot does not itself
exclude a directory: accessible eligible hidden paths follow the same rules as others.

You can intentionally leave a colleague's test tree alone, even when it is accessible:

```bash
python3 patch_miniforge_trust.py /actual/path/to/miniforge \
  --all-envs \
  --ca-bundle /actual/path/to/CSE-existing-bundle.pem \
  --exclude /actual/path/to/miniforge/.colleague-test
```

Exclusions apply to discovery and nested permission traversal. Add `--apply` only after
reviewing the preview. If `conda env list` fails, discovery attempts the local
`~/.conda/environments.txt` registry and still scans available configured scan roots
and the base installation's `envs` directory.

The final console report and private logs identify:
- `skipped`: an environment could not be inspected/maintained and was not updated.
- `updated-with-skips` / `previewed-with-skips`: selected work completed, but listed
  file/subtree permissions could not be normalized. Do not treat the skipped paths as
  remediated.
- `incomplete`: a package update, verification, or another required operation failed,
  or an environment became inaccessible after changes started.

`skipped-paths.txt` and `skipped-paths.json` contain full paths, stages, reasons,
owning usernames/UIDs, groups/GIDs and associated environments where known. The
path owner is looked up in the host account database; an unknown UID remains numeric,
and an inaccessible path whose ownership cannot be read is labeled unknown. No owner
is guessed from a parent directory.

`skipped-by-owner.json` groups the paths by owner. `skipped-owner-UID.txt` provides
a separate private text report for each owner (or `skipped-owner-unknown.txt`). You can
review and share the relevant report with that colleague; the script sends nothing.
These reports identify owners, not proof that a particular colleague caused the issue.
`summary.json` lists each selected prefix and status. Discovery cannot identify what
is inside an unreadable directory; such a directory is recorded as an uninspected
path rather than asserted to be a conda environment.

Access/ownership/ACL skips alone are nonfatal warnings (exit 0), and available
environments continue. `incomplete=4` in the console means four environments need review, not four package
versions and not process exit code 4. Each environment's reasons appear in the final
summary and `summary.json`. A permission/access skip alone is distinct from an
incomplete package/check operation. Actual package/check failures remain exit 2 after the remaining
environments have been attempted. Necessary base/CA-source/group validation and lock
failures still stop the run before it can safely proceed.

## Required cse permissions

| Item | Group | Mode |
| --- | --- | --- |
| Shared directories | cse | 2775 (setgid) |
| Ordinary shared files | cse | 0664 |
| Files already executable | cse | 0775 |

Existing sticky bits on directories are retained. Owner UID is preserved.
The target group is always `cse`, regardless of your primary group or the prefix's
previous group. Setgid enables group inheritance in newly created subdirectories.
Package installation permissions are normalized after a successful update.

Symlinks are not followed. Hardlinks are broken before mode/group changes to avoid
changing caches or other prefixes. Known secret paths, private configuration, privileged
files, extended ACLs and files owned by other accounts are preserved or reported for
review. Another owner's files can only be left unchanged if already compliant; group
write access alone does not permit chmod/chgrp. Parent directories and package-cache
contents are not recursively modified. Private parent traversal can still block access.

“Parent lacks other-traverse bit” means an ancestor directory lacks execute permission
for users outside its owner/group. Group membership or an ACL may still grant access;
this warning alone does not establish that everyone is blocked. Such paths are
reported under `parent-access`, with their actual owner where readable. The script
does not widen home directories or overwrite ACLs. Making an environment group `cse`
does not itself fix access through a private parent. For shared software, have the
parent owner/admin review traversal or move the environment into an approved shared
software location. All selected eligible environments, including ones in your home,
use the same `cse` group target; the user owner UID stays unchanged.

## Certificate behavior and activation

Certificate preparation reads the source PEM and writes a separate managed copy:

- `MINIFORGE/etc/cse-trust/ca-bundle.pem`
- `MINIFORGE/etc/cse-trust/use-ca.sh`

Writing this shared managed copy is the preparation stage. It happens before the
base package transaction and can remain after a package failure. Packages may replace their own
vendor PEM files inside selected prefixes, and successful selected prefixes receive
persistent `.condarc` and activation-variable changes; those are final changes,
not temporary staging. A package-owned source PEM inside a selected prefix can also
be replaced by its package update; external site/OS source files are only read.
With the default scope, those package/configuration changes
are confined to base. No bundle is copied over every discovered PEM path.
Environments already configured to use the shared managed bundle see its new contents
too, even when their own files are outside this run's scope. Use `--trust-only` for
managed-bundle preparation without package/configuration/permission updates.

The new bundle preserves certificates other than four exact incident-root fingerprints.
This is interim root-removal mitigation, not a complete refresh of your custom public
trust collection. Broad-root removal can affect legitimate chains. Organizational CAs
already in the selected source are retained; `--extra-ca /path/to/org-ca.pem` adds an
explicit additional CA. Private keys and trust-policy/AUX PEM inputs are rejected.

The conda CA packages and pip's embedded trust are updated separately, using conda-forge
packages. Existing conda-installed sigstore is also targeted at >=4.5.1; its dependencies
are solved together. If the required build cannot be obtained from the requested approved channels, the
prefix is reported incomplete rather than switching sources. After updating an installed
sigstore, the script runs `python -I -m sigstore --help` as a local startup check and
captures its errors or signal status. This is not a full signing/verification test and
does not establish that a coworker's unrelated runtime error is fixed. Supply the exact
failing command and traceback for that diagnosis. Sigstore is not added to prefixes
where it was absent.

An old environment
that cannot accept fixed package versions is reported for reviewed remediation.

Successful prefixes receive conda SSL configuration and conda activation variables.
Reactivate the environment after updating. For your current shell after loading the module:

```bash
MF="$(conda info --base)"
. "$MF/etc/cse-trust/use-ca.sh"
```

Add the equivalent environment settings to your site modulefile using your existing
Tcl/Lua conventions. The script does not edit an unknown modulefile.

## Results and limits

The printed private log directory contains `run.log`, configuration/history records,
solver plans, `certificate-status.json`, `summary.json`, `skipped-paths.txt`, `skipped-paths.json`,
`skipped-by-owner.json` and `skipped-owner-UID.txt`. Exit 0 allows
reported access/ownership skips; inspect the summary before declaring an installation
fully remediated. Exit 2 means incomplete package/check work or a critical startup
failure. Preview success is not a claim that a future dependency solve will succeed.

No incident-root match in a bundle is a screening result, not proof of full chain
rejection. Optionally use approved local test chains with `--chains-dir /path/to/chains`;
the script uses offline OpenSSL 3 verification and never downloads test material.
The proxy's upstream verification must be assessed separately by its maintainers.

Local tests cover the exact cse lookup/membership checks, file/directory modes,
foreign-owner reporting, hardlink isolation, secret exclusions, discovery, pinning,
CA filtering, quiet/verbose output, owner report grouping, final-summary reasons,
permission preview counts, read-only legacy-log reporting, structured command-failure
records, mixed-package review ordering, access-path snapshots, certificate-only
operations, actual-bundle inspection, exact-prefix scope, channel-source guards, per-environment installed-source discovery,
source-qualified update specs, malformed/host-only metadata recovery, structured alias/custom-channel config, full-base update policy, mandatory minimum
verification, one-transaction base updates, stale-plan/installed-version guards,
offline package policy, preservation of original before/after inventories, and
simulated preview/offline apply. Tests also cover newest-version selection when
the minimum is already installed, downgrade guards, stale metadata, and default
base-only scope with unchanged sibling PEM/configuration files. Actual SUSE/RHEL deployment remains
a target-system validation task.

To include the installed solver/allowlist and legacy-classic regressions:

```bash
CSE_CONDA_PYTHON=/path/to/miniforge/bin/python \
  python3 -m unittest discover -s scripts -p test_channel_regressions.py
```

Those checks verify the restricted libmamba runtime and retain coverage of the
legacy classic tuple/hint failure path.
It performs no package transaction or network access. Without `CSE_CONDA_PYTHON`,
that integration check is skipped.

## References

- [Conda guidance for pip in environments](https://docs.conda.io/projects/conda/en/stable/user-guide/tasks/manage-environments.html#using-pip-in-an-environment)
- [Conda incident guidance](https://conda.org/blog/2026-10-21-emudhra-security-updates/)
- [Python incident guidance](https://discuss.python.org/t/109576)
- [Git clone options](https://git-scm.com/docs/git-clone)
- [Git show](https://git-scm.com/docs/git-show)
- [OpenSSH scp](https://man.openbsd.org/scp)

