# Update a Miniforge base

Copy this folder's `README.md` and `patch_miniforge_trust.py` to each system.
No checkout or pull is needed; package operations use the approved package sources.
Load the usual site/compiler and Miniforge modules, then run from this folder
with Python 3.8+. Use the maintenance account (`cse` group), not root.
Only **base** is updated; other environments stay unchanged.

**Already updated, but missing the curl command?** With revision 30, use this
focused repair; you do not need to repeat staging/promotion:

```bash
python3 patch_miniforge_trust.py --repair-curl
python3 patch_miniforge_trust.py --repair-curl --apply
```

It installs matched Conda curl/libcurl and needed dependencies, refreshes native
PEMs/permissions, and checks the selected command and HTTPS. Unrelated application
changes are rejected. Users should reload the module or use `hash -r` to clear a
cached system curl. New stages now include curl and test its startup explicitly.

**1. Stage privately.** Build a candidate under your home. Use a new directory
name for each installation or retry.

```bash
cse_stage="$HOME/cse-base-review-1"
python3 patch_miniforge_trust.py --stage "$cse_stage"
```

**2. Review.** Require `ready-for-review`, read `review.md` and `comparison.csv`,
and check needed applications using the candidate in `$cse_stage/env`.

```bash
python3 patch_miniforge_trust.py --report "$cse_stage"
```

**3. Check access and preview promotion.** Resolve required permission blockers
and review the dry-run result before applying.

```bash
python3 patch_miniforge_trust.py --check-permissions --promote "$cse_stage"
python3 patch_miniforge_trust.py --promote "$cse_stage"
```

**4. Apply.** Use the normal maintenance window/recovery arrangements and stop
concurrent base jobs/updates. This installs the reviewed set and normalizes
eligible shared permissions. Review the final status and any skips.

```bash
python3 patch_miniforge_trust.py --promote "$cse_stage" --apply
```

**5. Filter the existing PEM files and check them.** No `use-ca.sh` step is needed.

```bash
python3 patch_miniforge_trust.py --trust-only --apply
python3 patch_miniforge_trust.py --inspect-trust
```

**6. Verify user operations.** In a fresh shell, reload the same modules and
return to this folder. Ideally run as an ordinary user, with a new test directory.
Read `verification.md` and require the requested checks to pass.

```bash
python3 patch_miniforge_trust.py --verify-user "$HOME/cse-user-check-1"
python3 patch_miniforge_trust.py --report "$HOME/cse-user-check-1"
```

Repeat separately for each GCC/Intel installation. If a step fails, stop and
bring Ravon the failing command and printed log directory. Do not reapply an old
stage after base has changed. Keep the update logs; `000-user-changes/README.md`
and its CSV/JSON files provide the user-facing package change list.

More detail, including test coverage and certificate-check limits:

```bash
python3 patch_miniforge_trust.py --base-guide
```
