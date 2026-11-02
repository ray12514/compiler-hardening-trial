# Miniforge base rollout: team handoff

Use the [short two-step README](miniforge-base-handoff.md) with revision 35 or newer.
Copy the updated script and README together; no repository checkout is needed on
the target system. Load the intended site/compiler and Miniforge module first.

## Required sequence: review/approve, then apply

```bash
python3 patch_miniforge_trust.py --promote
python3 patch_miniforge_trust.py --promote --apply
```

Review the first command's planned changes and require **Review READY** before
running the second. No old stage path, separate staging command, or preliminary
package update is needed. `--approve` is an alias for `--promote`.

An already updated base keeps its installed Conda, Python and application versions/
builds. Missing curl is matched to installed libcurl, with missing dependencies
added as needed. A matching installed pair skips package solve/installation.
Existing maintenance markers and stage directories are not prerequisites. For an
initial rollout or unmet security minimums, private candidate staging and its
promotion preview run automatically; review those additional changes.

Apply finds the saved review for the loaded installation. It uses the reviewed
package versions/builds/checksums, includes the filtered OS-to-native-PEM merge,
and normalizes eligible base/link permissions. OS bundle discovery covers RHEL
and SUSE. Known incident certificates/public keys are removed before writing and
native files are screened afterward. Administrator trust files remain unchanged.
No extra trust/merge/permissions command or `use-ca.sh` step is required.

Reviews live under `~/.cse-trust-reviews/`, separated by host and resolved base.
Every review and apply log gets a fresh directory. `--log-dir PATH` optionally
chooses a location; an existing name gets a new suffixed sibling without changing
its contents. The latest pointer selects a review; it does not overwrite review
artifacts. An unsuccessful new review cannot select an older ready review.

If the base, selected CA inputs, script revision or saved plan changes between
review and apply, the operation stops: run the same review command again, then
apply. After a successful apply, a later maintenance pass starts with a new
review; it does not need to rebuild an already updated base. Installation-specific
records prevent a GCC review from being used for an Intel prefix or another host.
Different machines do not need identical package versions.

Use the normal maintenance account (`cse` group), maintenance window/recovery
arrangements, and stop concurrent base jobs/updates before apply. Read final
status and owner/access skips; group membership cannot change another owner's
files. Other environments and the Miniforge installer are kept. Shared prefixes
mounted on several machines should be maintained once, without competing updates.

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
python3 patch_miniforge_trust.py --version  # revision 35 or newer
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

## Optional inspection and troubleshooting

The normal sequence already performs required checks. These are available when
needed; they are not additional mandatory rollout commands:

- `--report PRINTED_REVIEW_OR_RUN_DIR`: read saved review/run evidence without
  changes or network access. A saved review is not evidence of completed apply.
- `--inspect-trust`: inspect current native certificate files and configuration.
- `--check-curl --curl-url https://your-service.example/`: test the installed curl.
- `--verify-user NEW_HOME_DIR`: exercise private Conda/pip downloads, environment
  creation, activation, local wheel build and permissions as a representative user.
- `--trust-only`, `--repair-curl`, `--permissions-only`: independent focused repairs.

Fresh-shell/module reloads and normal application/user tests remain useful when
validating a rollout. Successful downloads do not prove rejection of every bad
chain. Optional `--chains-dir PATH` verifies supplied incident chains offline;
no live incident test sites are probed. If a step fails, give Ravon the failing
command and printed directory; do not repeatedly apply a failed/changed review.

Older explicit `--stage NEW_DIR`, `--report STAGE_DIR`, `--promote STAGE_DIR`,
`--promote STAGE_DIR --apply` workflows still work for existing operators. They
are an advanced/manual interface, not prerequisites for the two-step sequence.

## Record completion, then repeat for the next installation

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

Repeat the two commands after loading the next distinct GCC/Intel installation.
Do not use `--all-envs`, `--only`, remove other baseline environments or replace
the Miniforge installer in this rollout. Those other environments are a later
separate sweep.

For command details and failure-specific recovery, see the
[full maintenance reference](miniforge-trust-maintenance.md). The standalone
script's `--base-guide` prints the short ordered sequence without accessing an
installation, changing files or contacting the network.
