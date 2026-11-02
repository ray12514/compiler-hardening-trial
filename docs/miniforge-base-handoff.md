# Update a Miniforge base

Copy this folder's `README.md` and `patch_miniforge_trust.py` to each system.
Load the usual site/compiler and intended Miniforge module. Run with Python 3.8+
as the maintenance account (`cse` group), not root. Only **base** is maintained.
No checkout/pull or Miniforge installer replacement is needed.

## Already installed: use the same promotion commands

With revision 33, point `cse_stage` at that installation's completed review stage:

```bash
cse_stage="$HOME/cse-base-review-1"
python3 patch_miniforge_trust.py --promote "$cse_stage"
python3 patch_miniforge_trust.py --promote "$cse_stage" --apply
```

Review the preview's **planned changes** before applying. It keeps the installed
Conda, Python and application versions/builds. If only curl is missing, it adds
curl matching the installed libcurl and any missing dependencies. It does not
search for newer versions of unrelated packages. An already installed matched
pair needs no package solve or reinstall.

Apply also merges the OS CAs into the native Miniforge PEMs **through the incident
certificate/key filter**, checks the result, and normalizes eligible base/file/
symlink permissions. System CA discovery covers RHEL and SUSE/openSUSE locations
automatically, including the newer RHEL extracted PEM path. OS trust files stay
unchanged; known incident certificates cannot return through the merge. No separate trust/merge/permission command or
`use-ca.sh` step is needed. Read the final status, logs and any owner-review skips.

The stage must belong to this installation. Unrelated package/checksum drift is
rejected rather than overwritten. If the old stage is unavailable, use the normal
staging sequence below: a previously maintained base meeting the script's security
minimums keeps its installed versions/builds, so its comparison shows the remaining
changes. An incompatible matching curl solve stops for review.

## First rollout, or a new private review stage

**1. Stage privately.** Use a new directory name for each installation or retry.

```bash
cse_stage="$HOME/cse-base-review-2"
python3 patch_miniforge_trust.py --stage "$cse_stage"
```

A first rollout solves a fresh compatible base. A previously maintained base
keeps the installed set and adds the missing curl pair/dependencies. If required
security minimums are no longer met, a fresh compatible solve is required and its
additional changes appear in the review. Versions across machines need not match.

**2. Review.** Require `ready-for-review`, read `review.md` and `comparison.csv`,
and test needed applications in `$cse_stage/env`.

```bash
python3 patch_miniforge_trust.py --report "$cse_stage"
```

**3. Check access and preview.** Resolve required owner/admin blockers.

```bash
python3 patch_miniforge_trust.py --check-permissions --promote "$cse_stage"
python3 patch_miniforge_trust.py --promote "$cse_stage"
```

**4. Apply.** Use the normal maintenance window/recovery arrangements; stop
concurrent base jobs/updates. Packages, filtered native trust and permissions are
handled together. Review the final status and any skips.

```bash
python3 patch_miniforge_trust.py --promote "$cse_stage" --apply
```

**5. Verify user operations.** In a fresh shell, reload the same modules and
return to this folder. Ideally use an ordinary account and a new test directory.

```bash
python3 patch_miniforge_trust.py --verify-user "$HOME/cse-user-check-2"
python3 patch_miniforge_trust.py --report "$HOME/cse-user-check-2"
```

Read `verification.md` and require the requested checks to pass. Repeat separately
for each GCC/Intel installation. If a step fails, bring Ravon the failing command
and printed log directory. Keep the stage and update logs; `000-user-changes/README.md`
and its CSV/JSON files provide the user-facing package change list.

`--base-guide` prints this sequence. The focused `--repair-curl`, `--trust-only`,
`--check-curl`, `--inspect-trust` and `--permissions-only` commands remain available
for later diagnostics; they are not extra steps in this rollout.
