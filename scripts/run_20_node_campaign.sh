#!/bin/bash
#SBATCH --job-name=hardening-20
#SBATCH --nodes=20
#SBATCH --ntasks-per-node=92
#SBATCH --cpus-per-task=1
#SBATCH --hint=nomultithread
#SBATCH --exclusive
#SBATCH --time=12:00:00
#SBATCH --output=hardening-%j.log

# Supply site account/partition with sbatch flags. Stage all inputs beforehand.
# This script allocates no nested job and never downloads, installs or rebuilds packages.
set -euo pipefail
export TRIAL_ROOT="${TRIAL_ROOT:-$HOME/COMPILER_HARDENING}"
: "${SLURM_JOB_ID:?Submit this script with sbatch}"
: "${IO_DIR:?Set IO_DIR to an absolute shared trial I/O directory before submission}"
[[ "$TRIAL_ROOT" = /* && "$IO_DIR" = /* ]] || { echo 'Use absolute trial and I/O paths' >&2; exit 2; }
trial="$TRIAL_ROOT/runner/trial"
[[ -x "$trial" ]] || { echo "Missing installed driver: $trial" >&2; exit 2; }
nodes="${CAMPAIGN_NODES:-20}"
[[ "$nodes" =~ ^[0-9]+$ && "$nodes" -ge 2 && "$nodes" -le "${SLURM_JOB_NUM_NODES:?}" ]] || {
    echo 'Requested campaign node count exceeds the allocation or is invalid' >&2; exit 2;
}
for value in "${RUN_SERIAL:-1}" "${RUN_OSU:-1}"; do
    [[ "$value" = 0 || "$value" = 1 ]] || { echo 'RUN_SERIAL and RUN_OSU must be 0 or 1' >&2; exit 2; }
done
jobdir="$TRIAL_ROOT/results/batch/$SLURM_JOB_ID"
mkdir -p "$(dirname "$jobdir")"
mkdir "$jobdir" # A new directory prevents a requeue from silently mixing attempts.
printf 'Batch evidence: %s\n' "$jobdir"
run_logged() {
    local phase="$1"; shift
    printf '\nStarting %s at %s\n' "$phase" "$(date -u +%FT%TZ)"
    "$@" 2>&1 | tee "$jobdir/$phase.log"
}
run_logged reframe-ready "$trial" prepare-tests --check
if [[ "${RUN_OSU:-1}" = 1 ]]; then
    run_logged osu-ready "$trial" osu build --check
fi
run_logged build-audit "$trial" audit
# Verify all node grants and WEKA exclusions before any timings. No overlap
# option is added by this batch script. The controller still uses private mpirun.
run_logged placement "$trial" production --audit-only --nodes "$nodes" \
    --ranks-per-node all --result-pointer "$jobdir/placement.json"
if [[ "${RUN_SERIAL:-1}" = 1 ]]; then
    # One audited physical core on the batch host. Serial tests do not span 20 nodes.
    export CPUSET
    CPUSET=$(python3 - "$jobdir/placement.json" <<'PY'
import json, socket, sys
from pathlib import Path
out = Path(json.loads(Path(sys.argv[1]).read_text())['campaign'])
manifest = json.loads((out/'manifest.json').read_text())
layout = json.loads((out/manifest['conditions'][0]['layout']).read_text())
print(layout['hosts'][socket.gethostname().split('.')[0]]['cpus'][0])
PY
)
    for package in fftw hdf5 lapack; do
        run_logged "serial-$package" "$trial" test "$package" --pairs "${SERIAL_PAIRS:-10}"
    done
fi
# Run the largest requested layout first, so smaller scales cannot consume its budget.
# Auto geometry is recorded per layout. This is a density assessment, not a strong-scaling curve.
production_status=0
run_logged production "$trial" production --reframe --scope deployment \
    --nodes "$nodes" --ranks-per-node all --fields 3 --fft-plan measure \
    --fft-mib-per-rank "${FFT_MIB_PER_RANK:-1}" --io-mib-per-rank "${IO_MIB_PER_RANK:-1}" \
    --workloads fft,collective,independent,integrated \
    --pairs "${PAIRS:-20}" --target-seconds "${TARGET_SECONDS:-15}" \
    --max-steps "${MAX_STEPS:-32}" --checkpoint-every "${CHECKPOINT_EVERY:-4}" \
    --timeout 600 --budget-minutes "${PRODUCTION_MINUTES:-420}" \
    --max-checkpoint-gib "${MAX_CHECKPOINT_GIB:-16}" \
    --max-written-gib "${MAX_WRITTEN_GIB:-2048}" \
    --result-pointer "$jobdir/production.json" || production_status=$?
if [[ ! -f "$jobdir/production.json" ]]; then
    echo 'Production did not create a result pointer; inspect its log. OSU was not started.' >&2
    exit 1
fi
production_result=$(python3 - "$jobdir/production.json" <<'PY'
import json, sys
from pathlib import Path
print(json.loads(Path(sys.argv[1]).read_text())['campaign'])
PY
)
run_logged result-build-audit "$trial" audit --results "$production_result" \
    --result-pointer "$jobdir/result-build-audit.json"
audit_result=$(python3 - "$jobdir/result-build-audit.json" <<'PY'
import json, sys
from pathlib import Path
print(Path(json.loads(Path(sys.argv[1]).read_text())['audit'])/'audit.json')
PY
)
run_logged team-summary "$trial" summary --campaign "$production_result" --audit "$audit_result" \
    --output-dir "$jobdir/team-summary"
if [[ "$production_status" != 0 ]]; then
    echo 'Production is partial or failed. Its summary is retained; OSU was not started.' >&2
    exit "$production_status"
fi
if [[ "${RUN_OSU:-1}" = 1 ]]; then
    run_logged osu "$trial" osu test --reframe --after-production "$production_result" \
        --nodes "$nodes" --ranks-per-node all --pairs "${OSU_PAIRS:-20}" \
        --iterations 1000 --warmups 100 --timeout 600 \
        --budget-minutes "${OSU_MINUTES:-120}" --result-pointer "$jobdir/osu.json"
fi
printf '\nCampaign complete. Result pointers and phase logs: %s\n' "$jobdir"
