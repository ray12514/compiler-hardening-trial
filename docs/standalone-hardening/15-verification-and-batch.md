# Verify the builds, share the results, then submit 20 nodes

The 16 October results show small point estimates in both directions. They do
not establish zero overhead. The current team summary uses screenshot
transcriptions. Original build logs, installed artifacts and paired records
remain on the cluster. Verify those before interpreting the small differences.

## First: audit the existing builds

After pulling the repository, reinstall the driver without rebuilding packages:

```bash
export TRIAL_ROOT="$HOME/COMPILER_HARDENING"
python3 scripts/install_driver.py --trial-root "$TRIAL_ROOT"
"$TRIAL_ROOT/runner/trial" audit
```

Run where the saved private toolchain and installations are available. This
read-only audit does not run MPI, benchmarks, correctness suites, downloads or
compilation. It checks both arms of FFTW, HDF5, BLAS, LAPACK, UCX, Open MPI,
MPI FFTW and MPI HDF5:

- Installed artifact hashes, qualification/policy equality and dependency IDs.
- Private GCC 12.5 compiler paths, versions and current binary hashes.
- Actual CMake or verbose build compile commands against the effective vectors,
  including optimization/CPU settings and ordered hardening controls.
- Applicable ELF PIE, RELRO, NOW and non-executable-stack properties.

Saved `flags.txt` or a manifest alone cannot pass the compile-command check.
Canary/fortified symbols are observations: optimization and function eligibility
affect emission, so their absence alone does not fail a build. Shared-library
PIC and executable PIE are distinct. FORTIFY does not apply to Fortran source.
Exact vectors and compatibility reductions remain visible in the private
`audit.json`. Retained commands are evidence, not an attestation of every
historical compiler invocation. Passing does not re-run upstream test suites.

The command prints `results/build-audit/RUN/summary.txt` and `audit.json`.
Missing actual compile evidence yields **incomplete**. Mismatches yield
**failed**. Both exit nonzero. Understand the recorded reason before changing
flags or rebuilding. The audit files contain system paths and must stay private.

Connect an earlier result to those verified builds using its original production
directory. Repeat `--results` for several directories:

```bash
"$TRIAL_ROOT/runner/trial" audit --results /absolute/path/to/results/production/RUN
```

Both saved MPI/UCX/FFTW/HDF5 stack records must match the verified current
records. Missing historical manifests remain unverified.
`shareable-summary.json` contains only package names, statuses and evidence
counts. It omits paths, compiler commands and system identifiers, so it can be
shared for assessment without the private audit. Symbol counts are descriptive,
not a security score or a replacement for the flag/artifact checks.

## Next: submit the 20-node batch job

[run_20_node_campaign.sh](../../scripts/run_20_node_campaign.sh) requests 20
nodes, 92 task slots per node, one CPU per task, no SMT, an exclusive allocation
and 12 hours. These are site-editable requests. They do not guarantee 92 safe
cores: inventory discovers the actual grant, excludes whole WEKA-reserved
physical cores, and selects the common eligible capacity. MPI oversubscription
is disabled. The batch script does not add interactive overlap. Private
`mpirun` still uses Slurm internally. Add site account, partition, memory and
node-type options to `sbatch` as needed. Use homogeneous CPU nodes.

Prepare ReFrame and OSU before submitting. Build OSU offline on a representative
compute node instead if the login CPU differs:

```bash
"$TRIAL_ROOT/runner/trial" prepare-tests --check
"$TRIAL_ROOT/runner/trial" osu prepare
"$TRIAL_ROOT/runner/trial" osu build --jobs 4
export IO_DIR=/absolute/shared/path/to/dedicated-trial-io
sbatch scripts/run_20_node_campaign.sh
```

Phases run sequentially:

1. Check prepared inputs, audit builds, then audit all 20 nodes' placement.
2. Screen serial FFTW/HDF5/LAPACK on one audited core of the batch host. These
   are single-node checks, not 20-node LAPACK measurements.
3. Run FFTW, collective HDF5, independent HDF5 and integrated FFT/checkpoint
   workloads at 20 nodes and all eligible physical cores through ReFrame.
   Keep one ordinary caller fixed and switch compatible complete stacks
   (`scope=deployment`).
4. Audit the result identities and automatically generate the shareable
   one-page HTML/SVG/JSON, including a partial production result.
5. If production completed, run OSU through ReFrame. Collectives use the dense
   layout. Latency/bandwidth use exactly two ranks on two nodes. Native OSU
   units remain separate. See [the OSU runbook](12-osu-screen.md).

Defaults are 20 balanced pairs per MPI condition, three fields, reused measured
FFT plans, a 15-second calibration target, at most 32 iterations, 420 production
minutes and 120 OSU minutes. One pair is one full run and one reference run.
Planning/launch time remain separate from loop timing. The target is bounded
work, not a guaranteed sample duration.

Requested FFT and standalone I/O volumes start at 1 MiB/rank per field.
Balanced slab geometry can round up. At 20 x 92 ranks the three-field integrated
checkpoint is about 9.7 GiB. The checkpoint cap is 16 GiB and total logical-write
allowance is 2 TiB, including calibration/warmups. Memory, available-space and
I/O guards remain active. The runner can cap iteration counts before sampling
or retain partial results on budget exhaustion. Review actual work and pair
counts. Automatic geometry makes this a density assessment, not a scaling curve.

Environment overrides: `PAIRS`, `SERIAL_PAIRS`, `OSU_PAIRS`, `TARGET_SECONDS`,
`PRODUCTION_MINUTES`, `OSU_MINUTES`, `FFT_MIB_PER_RANK`, `IO_MIB_PER_RANK`,
`MAX_STEPS`, `CHECKPOINT_EVERY`, `MAX_CHECKPOINT_GIB`, `MAX_WRITTEN_GIB`.
Set `RUN_OSU=0` or `RUN_SERIAL=0` to
omit an optional phase. `CAMPAIGN_NODES` selects a smaller allocation subset.
Run smaller scales separately so they cannot consume the large-layout budget.
No job has been submitted by this update.

Logs and result pointers live under `results/batch/JOB_ID/`. Failures stop later
phases. Partial production does not pass ReFrame or start OSU, but its summary
retains complete pairs. Do not update the trial while queued or running.

## Regenerate the team summary

The current [one-page summary](../../output/team-summary-2026-10-21/team-summary.html)
shows 2-, 4- and partial 8-node dense results, missing cases and sample counts.
Those earlier `scope=stack` tests changed callers and libraries together.
Keep them separate from the next deployment comparison and from native OSU data.

```bash
"$TRIAL_ROOT/runner/trial" summary \
  --campaign /absolute/path/to/results/production/RUN \
  --audit /absolute/path/to/results/build-audit/AUDIT/audit.json \
  --output-dir "$TRIAL_ROOT/results/team-summary"
```

`--audit` is optional. Only a passed historical identity match lets the summary
label build verification complete. The generator recomputes estimates and 95%
paired bootstrap intervals from complete process pairs. It preserves partial
counts and rejects mixed scopes or duplicate conditions. Select at most 16
conditions per page. Repeat `--campaign` for compatible distinct layouts.
Show independent allocations on separate pages. Missing values never become
zero. No pooled overall effect, speedup or zero-overhead claim is generated.

`team-summary.html` works offline. Its SVG and metric-only JSON omit hostnames,
job IDs, installation paths and logs. These files can be shared. The current
briefing is in `output/team-summary-2026-10-21/`. Its first slide shows results
and coverage. Its second defines the constructed tests, pairing, time
interpretation and follow-up coverage. The original one-page result view is
retained alongside it. The editable slide
exporter is [reports/build_team_slide.mjs](../../reports/build_team_slide.mjs)
for a prepared desktop presentation runtime. Cluster-side HTML/SVG generation
needs no third-party plotting or presentation packages.

## Interpreting longer jobs

For unchanged work and a stable relative cost, a longer run accumulates more
absolute seconds, not a larger percentage. The conditional calculation is:

`added seconds = reference job seconds x runtime change percent / 100`

For example, a sustained **hypothetical** 1% whole-job slowdown adds 36 seconds
to one hour, 7.2 minutes to 12 hours, or 14.4 minutes to 24 hours. Those are
arithmetic examples, not predictions from this campaign. Repeating an operation
does not multiply its percentage penalty by the iteration or node count.

If the measurement describes only a library phase, account for the fraction of
job time in that phase. A hypothetical 1% increase in a phase occupying 40% of
an otherwise unchanged job gives about 0.4% extra total time. Synchronization
and overlapping phases can make this simple model insufficient.

The current point estimates cannot establish a sustained penalty or speedup.
Long jobs may change their I/O pattern, caching, contention, memory footprint,
thermal behavior or communication algorithms. Use original paired uncertainty
bounds and repeat representative longer fixed-work runs before predicting
whole-job impact. A longer repeated loop can improve measurement precision,
but it does not replace independent allocations or verify the build treatment.

### Coverage follow-up

The 20-node batch is the next density screen, not an hours-long performance
validation. Follow it with a separate FFT-only lane that lengthens measured
loops from seconds to minutes while keeping work identical between paired arms.
For example, inside an appropriate existing allocation, use:

```bash
"$TRIAL_ROOT/runner/trial" production --reframe --scope deployment \
  --nodes 20 --ranks-per-node all --workloads fft --fields 3 --fft-plan measure \
  --fft-mib-per-rank 1 --pairs 20 --target-seconds 120 --max-steps 4096 \
  --timeout 900 --budget-minutes 180
```

Retain `--slurm-overlap` only in the interactive environment that needs it.
The controller still calibrates and records actual step counts and loop times;
the requested target may be capped. Compare multiple grid sizes and fixed-work
definitions in separate campaigns. Twenty two-arm process pairs also test
stability over a longer allocation, but are not one continuous hours-long
application. An additional sustained trial should record time/order trends and
preserve matched work in each arm.

The current HDF5 lane covers contiguous datasets, writes plus flush/close,
repeated checkpoint replacement and a final warm read-back. It does not cover
every access pattern, cold-cache reads, physical durability, compression,
chunking or retained checkpoint history. Select representative checkpoint sizes,
cadences and read/write mixes before extending that lane. Account for total
I/O volume instead of merely running writes for hours. Repeat selected FFT and
I/O conditions in independent allocations. Keep individual-flag attribution
deferred until build verification and a repeatable performance signal justify it.

## Local implementation checks

All 87 automated checks passed, including real ReFrame 4.10.4 reporting,
build-evidence omissions/overrides, compiler selection, paired summaries and
complete/partial batch execution with a recording driver. Four real Linux ELF
fixtures exercised full/reference shared-library and executable controls in a
network-disabled container. The two-slide briefing passed structural/native
chart/table checks and visual review. These checks validate the implementation;
they do not verify the cluster's installed artifacts or qualify a 20-node run.
