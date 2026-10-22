# CSE Miniforge trust maintenance

The maintenance script is [scripts/patch_miniforge_trust.py](../scripts/patch_miniforge_trust.py).
It updates selected shared conda environments and builds a CSE-managed, incident-filtered
CA bundle from your existing site PEM. It leaves the OS and the inspection proxy unchanged.
No external incident test endpoint is contacted.

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

### Reproduce the skip-inaccessible revision exactly

The script was updated at commit `031c5b34a2cb463f8ddf0ba95d10e244b0fce153`.
For a reproducible download, use the SSH clone block above and add this command
immediately before its `git show` command:

```bash
git -C "$cse_fetch_dir/repo" fetch --depth 1 origin \
  031c5b34a2cb463f8ddf0ba95d10e244b0fce153
```

Then replace `HEAD:scripts/patch_miniforge_trust.py` with
`FETCH_HEAD:scripts/patch_miniforge_trust.py` in `git show`, and use
`rev-parse FETCH_HEAD` for the provenance record. Verify this exact script revision:

```bash
echo 'e1fca95d313a6d7ef904f47485229990988fb49c8e5b6c96728885768947698b  patch_miniforge_trust.py' |
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
permission-change counts and reported issues.

## Apply

Use your normal snapshot and maintenance-window process. The script saves private
configuration/history records, but does not create a filesystem or package snapshot.

```bash
python3 patch_miniforge_trust.py /actual/path/to/miniforge \
  --ca-bundle /actual/path/to/CSE-existing-bundle.pem \
  --apply
```

All install/solve commands explicitly use `--override-channels --channel conda-forge`
and strict channel priority. Other configured channels are not searched. Existing
`channel_alias`/custom-channel mappings for your approved conda-forge mirror still apply.
There is no PyPI or pip-install fallback. External conda plugins are disabled during
maintenance subprocesses to prevent conda-pypi from introducing another package source.
For disconnected operation, add `--offline`; the necessary conda-forge packages must
already be cached or available through the site's conda-forge mirror mapping.
Outdated pip-managed tools are reported for reviewed migration, without overwriting
pip-owned files automatically.

Conda itself is retained by default; add `--upgrade-conda` to request conda >=26.9.4.
Python and scientific packages keep their installed versions/builds. A blocked
dependency plan is reported rather than forcing a broad environment upgrade.

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

`skipped-paths.txt` and `skipped-paths.json` contain full paths, stages and reasons.
`summary.json` lists each selected prefix and status. Discovery cannot identify what
is inside an unreadable directory; such a directory is recorded as an uninspected
path rather than asserted to be a conda environment.

Access/ownership/ACL skips alone are nonfatal warnings (exit 0), and available
environments continue. Actual package/check failures remain exit 2 after the remaining
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
are solved together. If the required build cannot be obtained from conda-forge, the
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
solver plans, `summary.json`, `skipped-paths.txt` and `skipped-paths.json`. Exit 0 allows
reported access/ownership skips; inspect the summary before declaring an installation
fully remediated. Exit 2 means incomplete package/check work or a critical startup
failure. Preview success is not a claim that a future dependency solve will succeed.

No incident-root match in a bundle is a screening result, not proof of full chain
rejection. Optionally use approved local test chains with `--chains-dir /path/to/chains`;
the script uses offline OpenSSL 3 verification and never downloads test material.
The proxy's upstream verification must be assessed separately by its maintainers.

Local tests cover the exact cse lookup/membership checks, file/directory modes,
foreign-owner reporting, hardlink isolation, secret exclusions, discovery, pinning,
CA filtering and simulated preview/offline apply. Actual SUSE/RHEL deployment remains
a target-system validation task.

## References

- [Conda incident guidance](https://conda.org/blog/2026-10-21-emudhra-security-updates/)
- [Python incident guidance](https://discuss.python.org/t/109576)
- [Git clone options](https://git-scm.com/docs/git-clone)
- [Git show](https://git-scm.com/docs/git-show)
- [OpenSSH scp](https://man.openbsd.org/scp)
