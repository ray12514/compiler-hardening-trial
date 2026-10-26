# CSE Miniforge trust maintenance

The maintenance script is [scripts/patch_miniforge_trust.py](../scripts/patch_miniforge_trust.py).
It updates selected shared conda environments and builds a CSE-managed, incident-filtered
CA bundle from your existing site PEM. It leaves the OS and the inspection proxy unchanged.
No external incident test endpoint is contacted.

## Update Conda in the loaded installation first

Revision 13 keeps the existing Miniforge installation and discovers it from the
loaded module's `CONDA_EXE` or `conda` on `PATH`. No system name or explicit base
path is needed. After retrieving the current script, load your normal Miniforge
module and preview only its base environment:

```bash
python3 patch_miniforge_trust.py --base-only
```

Then apply that scope:

```bash
python3 patch_miniforge_trust.py --base-only --apply
```

The script detects the currently selected existing CA bundle as before. Use the
existing `--ca-bundle /path/to/CSE-existing-bundle.pem` option when a particular
site bundle is required. It reads that source and writes the filtered copy to
`BASE/etc/cse-trust/ca-bundle.pem`; it does not edit administrator trust files.
The CSE bundle and verified-TLS environment are prepared before either package
transaction. Afterward, source the printed `use-ca.sh` path in the current shell.

If installed base Conda is below `26.9.4`, apply first requests `conda>=26.9.4`,
`ca-certificates>=2026.10.19`, and `certifi>=2026.10.19`. This is a separate
targeted bootstrap solve/install, without `--update-all`; compatible dependencies
can change as part of that transaction. The bootstrap uses the same allowed
channels, source selection, classic solver, exact-plan checks, and `--offline`
policy as the remaining work. It does not run a Miniforge installer, change its
Spack version pin, remove the prefix, or replace the distribution.

Only after the installed Conda and CA-package minimums are verified does the
script run the existing full base update. A failed or unverified bootstrap stops
that prefix before the full update. A sufficiently new Conda skips the bootstrap.
Preview stays local-only and reports `would-update` or `not-needed`; it does not
solve, install, or contact package channels. `--trust-only` continues to perform
certificate-only work without invoking Conda or updating packages.

Private logs retain `base-conda-bootstrap-plan.json`,
`base-conda-bootstrap-install.json`, and a separate `conda_bootstrap` result in
`summary.json`. If the later full update fails, the report distinguishes a
completed Conda bootstrap from incomplete base-package work. The package-change
summary compares against the original pre-bootstrap inventory, so the manager
upgrade remains visible. A Conda package update changes contents of the existing
base tree; if that tree was installed by Spack, retain these maintenance records
because its Spack DAG hash does not change with this package transaction.

Other environments are not updated by `--base-only`. The normal existing
discovery/`--only` workflow remains available for a subsequent separately selected
environment, and user instructions can be prepared after the base is tested.

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
That historical revision performs the full base update but does not have the
separate Conda bootstrap above. Use the current `main` retrieval for revision 13.
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

Revision 13 first bootstraps an older Conda as described above, then retains
revision 12's full conda package-update scope for the Miniforge base. It no
longer rejects changes to `krb5`, NumPy, matplotlib, matplotlib-base, Python or other
base packages as unrelated. The base solve uses `--update-all` with no script-generated
version/build pins on application packages. Installed incident-related packages retain
explicit minimum constraints, and installed conda is targeted at >=26.9.4 automatically.
Conda resolves compatible versions using the permitted channels and retained site pins;
this does not promise every package will reach the newest version on every channel.

Use the same base-only command to isolate this work:

```bash
python3 patch_miniforge_trust.py /actual/path/to/miniforge \
  --base-only --ca-bundle /actual/path/to/CSE-existing-bundle.pem --apply
```

The validated solver plan is saved, then executed with exact final versions/builds.
New dependencies and updates to any base package are permitted. The Anaconda defaults
source exclusion, installed-source selection, dependency solving and rejection of
package removal without replacement remain in force. No `--no-deps` or `--clobber`
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

The base is selected first in normal discovery unless explicitly excluded. It is now
labeled `[BASE]` in scope/progress output. To isolate it and avoid discovering other
users' environments:

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

Where a package's source is identifiable and permitted, its requested spec is qualified
with that channel, for example `https://conda.anaconda.org/bioconda::PACKAGE>=VERSION`.
This preserves the source instead of silently moving the package to the first channel.
The final execution specs also retain identifiable solver-selected sources. If that
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
Defaults-qualified pins still block the prefix instead of causing default downloads;
other channel-qualified pins must resolve into that environment's selected source set.
Existing site pins are retained. Solver LINK/FETCH records referencing known Anaconda
defaults locations are rejected before executing the install.

An excluded historical source is reported; it is not a claim that the source was
contacted by this run. An unknown private mirror's upstream contents cannot be inferred
from its URL alone. This automatic reuse assumes the recorded non-default sources
were permitted for these existing environments; site source controls still apply.
There is no PyPI or pip-install fallback. External conda plugins are disabled during
maintenance subprocesses to prevent conda-pypi from introducing another package source.
For disconnected operation, add `--offline`; the necessary packages from the requested approved channels must
already be cached or available through the site mirror mapping.
Outdated pip-managed tools are reported for reviewed migration, without overwriting
pip-owned files automatically.

The base permits a full compatible package update, including conda >=26.9.4.
Other prefixes retain conda by default; add `--upgrade-conda` there to request that
minimum. Non-base Python and scientific packages keep their installed versions/builds.
Blocked dependency plans and unmet security minimums remain incomplete.

## Environment scope

Base and registered environments are discovered automatically, as are direct children
of the installation's `envs` directory. Eligibility requires actual maintenance access
through your UID or current groups. Registration alone is not ownership.

Add an unregistered environment with `--include /path/to/environment`. Find environments
under a known software directory with `--scan-root /path/to/shared/environments`.
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

The source PEM is read, not overwritten. The script writes:

- `MINIFORGE/etc/cse-trust/ca-bundle.pem`
- `MINIFORGE/etc/cse-trust/use-ca.sh`

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
verification, module-based bootstrap ordering, failed/stale bootstrap guards,
offline bootstrap policy, preservation of original before/after inventories, and
simulated preview/offline apply. Actual SUSE/RHEL deployment remains
a target-system validation task.

## References

- [Conda guidance for pip in environments](https://docs.conda.io/projects/conda/en/stable/user-guide/tasks/manage-environments.html#using-pip-in-an-environment)
- [Conda incident guidance](https://conda.org/blog/2026-10-21-emudhra-security-updates/)
- [Python incident guidance](https://discuss.python.org/t/109576)
- [Git clone options](https://git-scm.com/docs/git-clone)
- [Git show](https://git-scm.com/docs/git-show)
- [OpenSSH scp](https://man.openbsd.org/scp)

