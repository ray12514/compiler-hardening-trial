# Miniforge base rollout: team handoff

For a transferred folder containing just the script and a short README, use the
[short handoff instructions](miniforge-base-handoff.md). This page is the detailed
reference, including retrieval and historical report recovery.

Use this sequence for the remaining machines and each distinct GCC/Intel
Miniforge installation. Scope: refresh **base**, normalize its eligible shared
permissions, filter its existing PEM certificate files, and verify normal user
operations. Other baseline environments will be handled in a later sweep.

The installed Miniforge distribution, prefix and module/Spack selection are kept.
Existing user environments, including `BASE/envs/*`, are not updated or deleted.
Different installations get their own stage, review, promotion and reports. If
multiple machines mount the same shared installation, update that installation
once rather than running competing updates against it.

## 1. Retrieve the script and short README, then load the intended setup

Use your usual GitHub SSH access. Run this from the intended handoff directory.
It writes the standalone script and short guide (`README.md`) into that current
directory, along with their source commit record. No repository checkout is kept:

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
  git -C "$cse_fetch_dir/repo" show HEAD:docs/miniforge-base-handoff.md \
    > ./README.md
  git -C "$cse_fetch_dir/repo" rev-parse HEAD > ./patch_miniforge_trust.commit
)
```

The script and README come from the same commit. Open `README.md` for the short
step-by-step sequence; copy these files together when handing off to a teammate.

Omit `--filter=blob:none` if the site's Git is too old to support it. Load the
site's usual environment/compiler modules, then its intended Miniforge module.
Start with a fresh shell when switching between GCC and Intel setups so old
activation/export settings do not select the previous installation or CA file.

```bash
python3 patch_miniforge_trust.py --version  # revision 29 or newer
python3 patch_miniforge_trust.py --base-guide
```

The script discovers the base from `CONDA_EXE` or `conda` on `PATH` and reports
the path it selected. Confirm it is the intended installation. No system name
is needed. If the loaded setup is ambiguous, every operation also accepts an
explicit Miniforge path before its flags.

Private staging needs read access to base and write access in your home. Shared
promotion and native PEM maintenance require the maintenance account's effective
access and membership in the exact `cse` group. Do not run as root. Normal user
verification needs no maintenance write access or `cse` membership.

## 2. Build a private candidate under your home

Choose a new stage name for this installation. Change the name for another
machine/installation or a retry; an existing stage directory is not reused.

```bash
cse_stage="$HOME/cse-base-review-1"
python3 patch_miniforge_trust.py --stage "$cse_stage"
```

This installs the candidate at `$cse_stage/env`, with private caches, temporary
trust files and comparison reports beside it. The shared base is read only in
this step. Its installed application requests seed a fresh compatible solve;
old version/build pins are not carried into the candidate. Required security
minimums still apply. Conda selects compatible available packages from approved
channels; it does not compile every package from source or guarantee every
package's individually newest version.

**Stop if staging fails.** The failed result and command output stay in the
stage directory. Do not promote an incomplete candidate. See the detailed
[staging and troubleshooting reference](miniforge-trust-maintenance.md).

## 3. Review and accept the candidate

```bash
python3 patch_miniforge_trust.py --report "$cse_stage"
```

Review `$cse_stage/review.md` and `comparison.csv`. Require `ready-for-review`,
then check the actual versions/builds, security results, additions, changes,
omissions and source access warnings. `not-selected` means an old package is
absent from the new graph; it is not proof that the package is deprecated or
unavailable. Read `candidate-requests.txt` to see retained application requests.

Run the normal application smoke tests using `$cse_stage/env/bin/python` or other
candidate executables. Include Intel/MPI/scientific-library checks where the
installation needs them. A successful dependency solve and manager startup do
not establish that every application or external site library works.

Do not silently discard an application to obtain a passing solve. If an omission
is intentionally accepted, use a new stage with the documented `--stage-skip`
option and review that result. Retain the accepted stage and reports.

## 4. Resolve permission blockers before promotion

Run as the account that will perform the shared update:

```bash
python3 patch_miniforge_trust.py --check-permissions --promote "$cse_stage"
```

Read the printed private permission report directory. It groups repair targets
by owner and identifies inspection gaps. Resolve blockers and rerun the scan.
This is a report, not a permission repair command. `cse` membership does not
permit changing another owner's permissions or bypassing ACLs. Use the reported
owner/admin repair process for those paths.

Every promotion also runs this preflight automatically. A blocker needed for
the accepted transaction stops it before base changes. Read-only inspection
cannot guarantee access to every future path or filesystem policy.

## 5. Validate and promote the accepted set to base

Use the normal maintenance window, snapshot/recovery arrangements and site
coordination; stop concurrent base updates and jobs using files being replaced.
Keep the same intended site/Miniforge setup loaded:

```bash
python3 patch_miniforge_trust.py --promote "$cse_stage"
python3 patch_miniforge_trust.py --promote "$cse_stage" --apply
```

Run the apply command only after the dry run succeeds and the reviewed result is
accepted. It installs the accepted package set at the original base path,
verifies it, and normalizes eligible base permissions to `cse`: directories
`2775`, ordinary files `0664`, existing executables `0775`. Owner UIDs are kept;
protected, foreign-owned or ACL-controlled paths can be skipped for review.

**Read the final status and exact printed log directory.** Use `--report` with
that directory. `updated-with-skips` requires reviewing its skip reports; a zero
exit code alone does not mean every path's permissions were changed. A failed
transaction can leave partial work: inspect its reports/recovery instructions
before retrying. Keep the promotion logs, accepted manifest and package records.

The stage is tied to its original source state. If base package/control metadata
changed after staging, create a new stage and review it. After a successful
promotion, do not reapply the old stage to repair a later certificate or user
test failure. Use that step's diagnostics instead.

## 6. Filter the installed native PEM files

Run this **after** package installation, because package updates can replace
their PEM files:

```bash
python3 patch_miniforge_trust.py --trust-only
python3 patch_miniforge_trust.py --trust-only --apply
python3 patch_miniforge_trust.py --inspect-trust
```

This filters the existing base `ssl`, certifi and pip-vendored certificate bundles
for the four known incident-root fingerprints. Already-clean files are not
rewritten. Unrelated/organizational CAs are retained. Administrator/OS trust
files are not modified; out-of-prefix PEM symlink targets are refused.

Promotion currently writes the earlier shared CSE trust configuration. This
native-PEM step redirects only those script-created base settings to the native
PEM and removes its saved empty-directory override. **Do not source `use-ca.sh`
for this sequence**, even if the promotion output prints that older instruction.
The native files are the intended final trust location. If a previous shell
still has old CSE exports, clear them or start a fresh shell; a child process
cannot change its parent's exports. Other custom trust settings are preserved
and must be reviewed if inspection reports them.

Require native bundle inspection to succeed. This is fingerprint screening;
full chain rejection is a separate optional offline test below. Broad-root
filtering can affect legitimate chains, so keep normal package-access tests.

## 7. Verify normal user operations

In a fresh shell, load the same site's normal modules and Miniforge. Ideally run
as a representative ordinary user, using that user's own home directory:

```bash
python3 patch_miniforge_trust.py --verify-user "$HOME/cse-user-check-1"
python3 patch_miniforge_trust.py --report "$HOME/cse-user-check-1"
```

The test directory must be new. It creates a private environment and checks
Conda creation/install, pip HTTPS download/install, a tiny local wheel build,
activation, imports, private write/rename/delete access and unchanged base
metadata/PEMs. Read `verification.md`; require the requested checks to pass.
No shared permission changes or base package updates happen in this mode.

For approved incident chains already available locally, add `--chains-dir PATH`
to verification. They are checked offline using OpenSSL 3. Without them,
`offline-chain-rejection` is explicitly `not-tested`; successful downloads and
clean root fingerprints alone do not establish rejection of every bad chain.
No live incident test sites are probed. Tests cover the account and operations
actually exercised, not every user's login files, all applications or proxy
upstream policy. Include normal application tests from step 3.

## 8. Record completion, then repeat for the next installation

### Generate the user-facing package change list

Revision 29 automatically saves `000-user-changes/README.md`, `packages.csv`,
`packages.json` and `manifest.json` in the printed private update log directory
after it verifies the installed package inventory. The list contains every
Conda-managed package: added, removed, changed version, changed build or unchanged,
with before/after versions and build identifiers. Version changes are not
necessarily upgrades. A package-only list does not certify permissions or TLS.

For an installation already updated, generate the same shareable files from its
saved **promotion/update** log directory, not a later certificate-only or user
test directory:

```bash
python3 patch_miniforge_trust.py --export-changes /path/to/completed-promotion-log \
  --changes-output "$HOME/miniforge-release-notes/base-update-1"
```

This reads saved files only: no module, shared write access, network, dependency
solve or rebuild is needed. The output directory must be new. Without
`--changes-output`, output goes into the saved run's new `user-changes` directory.

Evidence labels distinguish what can be recovered:

| Label | Available evidence |
| --- | --- |
| `verified-installed` | Full recorded installed inventories, or an older saved approval manifest matched to a recorded successful package promotion |
| `limited-installed-summary` | An older successful update summary lists some actual changes; build IDs and unchanged/unrecorded packages may be unavailable |
| `candidate-only` | A ready stage comparison, clearly headed **NOT INSTALLED**; it does not establish a completed rollout |

Older successful promotions retain both original versions/builds and the accepted
set in `approved-promotion-plan.json`; the original private candidate directory
does not have to remain available for that reconstruction. Missing or inconsistent
evidence is reported rather than replaced by assumptions about today's installed
base. Failed/incomplete candidates are not exported as completed package lists.

Review the output and rollout status before publication. Copy **only** these four
generated files into the approved user-readable documentation/storage location,
with a distinct machine/installation/date folder, and add its link to the
[Miniforge update index](miniforge-updates/README.md). Do not give users the private
run logs, raw inventory/explicit package URLs or permission-owner reports. The
export omits those details and credentials. Its files have readable modes, but
private home/log-directory parents can still prevent other users from reading
them; check access from an ordinary user account at the final published location.
No upload, publication, user notification or index entry is created automatically.

### Retain the maintenance record

Keep the script's source commit, selected base path, loaded setup, accepted stage
and comparison, promotion/permission reports, certificate results and user test
results together. Record remaining skips and any intentionally untested checks.
Keep these records with a Spack-installed base: its original DAG hash does not
change when Conda updates the contents.

Repeat with fresh stage/test names for the next distinct GCC/Intel installation.
Do not use `--all-envs`, `--only`, remove other baseline environments or replace
the Miniforge installer in this rollout. Those other environments are a later
separate sweep.

For command details and failure-specific recovery, see the
[full maintenance reference](miniforge-trust-maintenance.md). The standalone
script's `--base-guide` prints the short ordered sequence without accessing an
installation, changing files or contacting the network.
