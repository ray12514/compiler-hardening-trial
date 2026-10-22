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

### Reproduce the cse-permissions revision exactly

The script was updated at commit `0e591c1d1d4ece947f16f60220794a390d64f52f`.
For a reproducible download, use the SSH clone block above and add this command
immediately before its `git show` command:

```bash
git -C "$cse_fetch_dir/repo" fetch --depth 1 origin \
  0e591c1d1d4ece947f16f60220794a390d64f52f
```

Then replace `HEAD:scripts/patch_miniforge_trust.py` with
`FETCH_HEAD:scripts/patch_miniforge_trust.py` in `git show`, and use
`rev-parse FETCH_HEAD` for the provenance record. Verify this exact script revision:

```bash
echo '8cfae07c90281f67b5e8703c7ace1ddc6a764af923338daeab66def90a62b387  patch_miniforge_trust.py' |
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

Normal apply uses the installation's configured channels/mirrors. Pip-managed tools,
if present and outdated, use PyPI. For disconnected operation, add `--offline`;
required conda packages must already be cached or available through configured local
file channels. Pip-managed packages requiring updates are reported separately in that mode.

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

The conda CA packages and pip's embedded trust are updated separately. An old environment
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
solver plans and `summary.json`. Exit 0 means the selected operation completed without
reported issues; exit 2 means skipped/incomplete work or a failure. Preview success is
not a claim that a future dependency solve will succeed.

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
