# Single allocation campaign with selected nodes

Use this optional mode after building and qualifying 00–06 and 11 and generating the inventory/collector from [08](08-slurm-campaign.md). One Slurm batch job holds **eight, four, or two homogeneous nodes** and runs a predetermined plan on subsets of those nodes. The [separate-job campaign](08-slurm-campaign.md) remains the fallback and the route for additional independent allocations. No Flux installation is needed.

Use the complete-stack builds/reference callers in [11](11-stack-comparison.md) before the primary campaign. Set `TRIAL_SCOPE=stack`, `CAMPAIGN_COMPARATORS=reference`, `RUN_PIE=0`. Package/PIE attribution uses library scope in a later campaign; PIE callers are required only with `RUN_PIE=1`. This mode uses the same scopes as 08 and remains outside CI.

## 1. Scope and execution order

Each round runs FFTW/LAPACK CPU cases (and PIE callers only for selected attribution) on every host, then HDF5 serial cases on every host, then the selected MPI scales. CPU cases can run concurrently on disjoint hosts; HDF5 and MPI conditions run sequentially. This avoids concurrent benchmark I/O/network traffic from this campaign. `process_elapsed` still includes launch/capture costs; classify these results with the recorded execution policy.

For each MPI scale, split a rotated host list into disjoint groups. Eight nodes yield eight one-node groups, four two-node groups, two four-node groups and one eight-node group per rank layout. Rotate the list each round so pair/group composition changes where possible. The eight-node set itself remains the same. Both hardening arms always use the same selected hosts, cores and inputs. Existing MPI callers check rank counts and hostnames; the updated harness also rejects a launch on the wrong host subset.

`TRIAL_ROUNDS=3` means three rounds **within one allocation**, not three independent allocations. Keep host/group/round estimates separate. Time-separated rounds and different hosts provide useful initial variation; they do not establish reproducibility across new allocations or all hardware. Keep pair/round budgets fixed before running and use [08's repeatability guidance](08-slurm-campaign.md#repeatability-and-a-manageable-first-assessment) for interpretation.

Slurm's [`srun`](https://slurm.schedmd.com/srun.html) supplies explicit node/resource selection for serial workers. MPI workers are launched by the batch controller, outside a resource-holding `srun` worker; private Open MPI then launches its own Slurm steps with a [`--host` filter](https://www.open-mpi.org/faq/?category=running#mpi-host) and no oversubscription. This retains the private Open MPI/UCX path and avoids depending on direct `srun` PMI compatibility. Qualify this step/placement behavior on the site's actual Slurm before the larger campaign.

## 2. Choose inputs

First regenerate `bench/paired.py` from 01, `reframe/hardening.py` from 06, and `reframe/inspect-node.sh` and `reframe/collect-campaign.py` from 08. Use those file-creation blocks; skip 08's separate-job submission commands when choosing this mode. The additions below are Python/Bash files, not compiled binaries. Existing qualified package/caller binaries can be reused. Use the qualified Python 3.10+ environment required by 06.

Retain the site inputs from 08: `TRIAL_ROOT`, `TRIAL_MODULE_SETUP`, optional `TRIAL_MPI_TUNING`, Slurm account/partition/constraint, shared I/O directory and any optional dedicated local I/O directory. Set:

```bash
export TRIAL_ALLOCATION_NODES=8  # choose 8, 4, or 2 before submission
export TRIAL_ROUNDS=3 PAIRS=20
export NODE_COUNTS='1 2 4 8' RANK_LAYOUTS='1'
export RUN_WEAK=0 CAMPAIGN_COMPARATORS=reference
export TRIAL_CPU_PARALLEL=1  # 0 for sequential CPU cases/initial qualification
export TRIAL_WALLTIME=04:00:00  # size from the pilot; 24:00:00 only if justified/site-permitted
export TRIAL_EXCLUSIVE=1
export TRIAL_REGRESSION_LIMIT_PERCENT=''  # descriptive unless a limit was predeclared
```

For site qualification, use two nodes, one round, ten pairs, `NODE_COUNTS='1 2'` and `TRIAL_CPU_PARALLEL=0`. A full eight-node plan has many host/group comparisons; estimate walltime from the pilot rather than assuming it finishes in four hours. Four allocated Slurm task slots per node permit either a four-core serial/threaded worker or up to four MPI ranks per node. The initial rank layout remains one rank per node.

## 3. Create the worker

The worker shares the workload definitions and paired analysis from 06. Serial steps must execute on their selected host; MPI uses the selected host list passed to private `mpirun`. `MPI_EXTRA_ARGS` is reserved for that placement here; put qualified UCX transport settings in `TRIAL_MPI_TUNING` as in 00b.

```bash
cat > "$TRIAL_ROOT/reframe/allocation-worker.sh" <<'SH'
#!/bin/bash
set -euo pipefail
phase=${1:?serial-cpu, serial-io, mpi-strong or mpi-weak}
source "$TRIAL_MODULE_SETUP"
source "$TRIAL_ROOT/env.sh"
export REFRAME="$TRIAL_ROOT/tools/reframe-venv/bin/reframe"
export TRIAL_ALLOCATION_MODE=single-allocation TRIAL_REPEAT_SCOPE=within-allocation-round
dest="$TRIAL_ROOT/results/campaigns/$CAMPAIGN_ID/$TRIAL_RUN_LABEL"
mkdir -p "$dest"
printf '%s\n' "$TRIAL_SELECTED_HOSTS" > "$dest/selected-hosts.txt"
if [[ "$phase" == serial-* ]]; then
    python3 - <<'PY'
import os, socket
expected=os.environ['TRIAL_SELECTED_HOSTS'].split(',')
if len(expected)!=1 or socket.gethostname().split('.')[0]!=expected[0].split('.')[0]:
    raise SystemExit('Serial worker is not on its selected host')
PY
    export MPI_NP=0 FFT_THREADS=4
    cpus=$(python3 - <<'PY'
import os
cpus=sorted(os.sched_getaffinity(0))
if len(cpus)<4: raise SystemExit('Need four allocated CPUs for serial/threaded workers')
print(','.join(map(str,cpus[:4])))
PY
)
    export THREAD_CPUSET="$cpus" CPUSET="${cpus%%,*}"
else
    source "$TRIAL_ROOT/mpi-env.sh"
    if test -n "${TRIAL_MPI_TUNING:-}"; then source "$TRIAL_MPI_TUNING"; fi
    unset UCX_LOG_LEVEL
    export MPI_NP=$((TRIAL_EXPECTED_NODES*RANKS_PER_NODE))
    export MPI_MAP="ppr:$RANKS_PER_NODE:node" HDF5_SCALING_MODE=${phase#mpi-}
    export MPI_EXTRA_ARGS="--host $TRIAL_SELECTED_HOSTS --nooversubscribe"
fi
run_group() {
    local group=$1 workloads=$2 comparators=$3 io=$4
    export WORKLOADS="$workloads" COMPARATORS="$comparators" IO_DIR="$io"
    export RUN_ID="$CAMPAIGN_ID-$TRIAL_RUN_LABEL-$SLURM_JOB_ID-$group"
    mkdir -p "$IO_DIR" "$TRIAL_ROOT/results/reframe/$RUN_ID"
    df -T "$IO_DIR" > "$dest/$group-filesystem.txt"
    printf '%s\n' "$RUN_ID" >> "$dest/sessions.txt"
    "$REFRAME" -C "$TRIAL_ROOT/reframe/settings.py" -c "$TRIAL_ROOT/reframe/hardening.py" \
      -r --exec-policy=serial --performance-report \
      --prefix="$TRIAL_ROOT/results/reframe/$RUN_ID/rfm" \
      --report-file="$TRIAL_ROOT/results/reframe/$RUN_ID/report.json" \
      2>&1 | tee "$TRIAL_ROOT/results/reframe/$RUN_ID/console.log"
}
unset MAX_SLOWDOWN_PERCENT
case "$phase" in
  serial-cpu)
    run_group cpu fft-small,fft-large,fft-3d,fft-plan,fft-threads,lapack-small,lapack-large,fft-startup,lapack-startup \
      "$CAMPAIGN_COMPARATORS" "$SHARED_IO_DIR"
    if test "${RUN_PIE:-0}" = 1; then run_group cpu-pie fft-pie,lapack-pie minus-pie "$SHARED_IO_DIR"; fi ;;
  serial-io)
    run_group io hdf5-small,hdf5-metadata,hdf5-contiguous,hdf5-chunked,hdf5-startup \
      "$CAMPAIGN_COMPARATORS" "$SHARED_IO_DIR"
    if test "${RUN_PIE:-0}" = 1; then run_group io-pie hdf5-pie minus-pie "$SHARED_IO_DIR"; fi
    if test -n "${TRIAL_LOCAL_IO_DIR:-}"; then
      run_group local-io hdf5-small,hdf5-metadata,hdf5-contiguous,hdf5-chunked \
        "$CAMPAIGN_COMPARATORS" "$TRIAL_LOCAL_IO_DIR"
    fi ;;
  mpi-strong)
    run_group strong fft-mpi-small,fft-mpi,fft-mpi-large,fft-mpi-plan,hdf5-collective,hdf5-independent,hdf5-mpi-small \
      "$CAMPAIGN_COMPARATORS" "$SHARED_IO_DIR" ;;
  mpi-weak)
    run_group weak hdf5-collective,hdf5-independent,hdf5-mpi-small \
      "$CAMPAIGN_COMPARATORS" "$SHARED_IO_DIR" ;;
  *) exit 2 ;;
esac
SH
chmod +x "$TRIAL_ROOT/reframe/allocation-worker.sh"
```

## 4. Create the plan and controller

`--validate` checks inputs and required payloads before submission. At job start the controller records actual hosts, inputs and the planned steps in `allocation-plan.json`. Every step is updated to running/passed/failed; later steps are marked not run after a failure. Larger-than-allocated scales are explicitly `skipped_capacity`. CPU steps form a barrier before any HDF5/MPI step begins.

```bash
cat > "$TRIAL_ROOT/reframe/allocation-controller.py" <<'PY'
import json, math, os, pathlib, re, signal, subprocess, sys, time

def configuration():
    env=os.environ
    for name in ('TRIAL_ROOT','TRIAL_MODULE_SETUP','SLURM_ACCOUNT','SLURM_PARTITION','SHARED_IO_DIR'):
        if not env.get(name): raise ValueError(f'Missing {name}')
    def positive(name, default):
        value=env.get(name,default)
        if not re.fullmatch(r'[1-9][0-9]*',value): raise ValueError(f'Invalid {name}')
        return int(value)
    def choices(name, default, allowed):
        values=env.get(name,default).split()
        if not values or len(set(values))!=len(values) or any(v not in allowed for v in values):
            raise ValueError(f'Invalid {name}')
        return [int(v) for v in values]
    config={'nodes':positive('TRIAL_ALLOCATION_NODES','8'), 'rounds':positive('TRIAL_ROUNDS','3'),
            'pairs':positive('PAIRS','20'), 'scales':choices('NODE_COUNTS','1 2 4 8',{'1','2','4','8'}),
            'layouts':choices('RANK_LAYOUTS','1',{'1','4'})}
    if config['nodes'] not in (2,4,8) or config['pairs']<2: raise ValueError('Invalid nodes/pairs')
    for name,default in (('RUN_WEAK','0'),('TRIAL_CPU_PARALLEL','1'),('TRIAL_EXCLUSIVE','1')):
        value=env.get(name,default)
        if value not in ('0','1'): raise ValueError(f'Invalid {name}')
        config[name]=int(value)
    comparators=env.get('CAMPAIGN_COMPARATORS','reference').split(',')
    allowed={'reference','minus-stack','minus-fortify','minus-relro','minus-now'}
    if len(set(comparators))!=len(comparators) or any(p not in allowed for p in comparators):
        raise ValueError('Invalid CAMPAIGN_COMPARATORS')
    limit=env.get('TRIAL_REGRESSION_LIMIT_PERCENT','')
    if limit and (not math.isfinite(float(limit)) or float(limit)<0): raise ValueError('Invalid limit')
    root=pathlib.Path(env['TRIAL_ROOT'])
    if not root.is_absolute() or any(c.isspace() for c in str(root)): raise ValueError('Invalid TRIAL_ROOT')
    required=[root/'tools/reframe-venv/bin/reframe',root/'reframe/allocation-worker.sh',
              root/'reframe/inspect-node.sh',root/'reframe/settings.py',root/'reframe/hardening.py',
              root/'reframe/collect-campaign.py',root/'bench/paired.py',root/'mpi-env.sh',
              pathlib.Path(env['TRIAL_MODULE_SETUP'])]
    if env.get('TRIAL_MPI_TUNING'): required.append(pathlib.Path(env['TRIAL_MPI_TUNING']))
    for path in required:
        if not path.is_file(): raise ValueError(f'Missing file: {path}')
    for package in ('fftw','hdf5','lapack','fftw-mpi','hdf5-mpi'):
        driver=root/'bench'/f'{package}-fixed'
        if not os.access(driver,os.X_OK): raise ValueError(f'Missing executable: {driver}')
        for p in ['full',*comparators]:
            if package=='lapack' and p=='minus-fortify': continue
            if not (root/'install'/package/p/'lib').is_dir(): raise ValueError(f'Missing {package}/{p}')
    scope=env.get('TRIAL_SCOPE','stack');run_pie=env.get('RUN_PIE','0')
    if scope not in ('stack','library') or run_pie not in ('0','1'): raise ValueError('Invalid scope/PIE selection')
    config['scope'],config['RUN_PIE']=scope,int(run_pie)
    if scope=='stack':
        if comparators!=['reference'] or run_pie!='0': raise ValueError('Stack screen requires reference and no PIE attribution')
        for path in (root/'mpi-env-reference.sh',root/'bench/rank-exec.sh',
                     root/'install/blas/full/lib/libblas.so',root/'install/blas/reference/lib/libblas.so'):
            if not path.is_file(): raise ValueError(f'Missing stack prerequisite: {path}')
        for package in ('fftw','hdf5','lapack','fftw-mpi','hdf5-mpi'):
            if not os.access(root/'bench'/f'{package}-reference',os.X_OK): raise ValueError('Missing reference caller')
    if run_pie=='1':
        for package in ('fftw','hdf5','lapack'):
            if not os.access(root/'bench'/f'{package}-minus-pie',os.X_OK): raise ValueError('Missing PIE caller')
    return config

def main():
    config=configuration()
    if sys.argv[1:]==['--validate']:
        print(json.dumps(config,indent=2)); return 0
    if sys.argv[1:]: raise ValueError('Use --validate or no arguments')
    root=pathlib.Path(os.environ['TRIAL_ROOT'])
    dest=root/'results'/'campaigns'/os.environ['CAMPAIGN_ID']
    dest.mkdir(parents=True,exist_ok=True)
    slurm=pathlib.Path(os.environ['SLURM_BINDIR'])
    hosts=subprocess.check_output([str(slurm/'scontrol'),'show','hostnames',os.environ['SLURM_JOB_NODELIST']],text=True).split()
    if len(hosts)!=config['nodes'] or int(os.environ['SLURM_JOB_NUM_NODES'])!=len(hosts):
        raise ValueError('Actual allocation size differs from requested size')
    if any(not re.fullmatch(r'[A-Za-z0-9_.-]+',h) for h in hosts) or len({h.split('.')[0] for h in hosts})!=len(hosts):
        raise ValueError('Invalid or ambiguous host identities')
    (dest/'allocated-hosts.txt').write_text('\n'.join(hosts)+'\n')
    with (dest/'slurm-job.txt').open('w') as log:
        subprocess.run([str(slurm/'scontrol'),'show','job',os.environ['SLURM_JOB_ID']],stdout=log,check=True)
    steps=[]
    def add(round_id,phase,group,nodes,rpn,available=True):
        steps.append({'label':f'r{round_id:02d}-{phase}-n{nodes}-p{rpn}-g{len(steps)+1:04d}',
                      'round':round_id,'phase':phase,'hosts':group,'nodes':nodes,'rpn':rpn,
                      'status':'pending' if available else 'skipped_capacity'})
    for round_id in range(1,config['rounds']+1):
        offset=(round_id-1)%len(hosts); rotated=hosts[offset:]+hosts[:offset]
        for phase in ('serial-cpu','serial-io'):
            for host in rotated: add(round_id,phase,[host],1,1)
        for rpn in config['layouts']:
            for nodes in config['scales']:
                phases=['mpi-strong']+(['mpi-weak'] if config['RUN_WEAK'] else [])
                for phase in phases:
                    if nodes>len(hosts): add(round_id,phase,[],nodes,rpn,False)
                    else:
                        for start in range(0,len(hosts),nodes): add(round_id,phase,rotated[start:start+nodes],nodes,rpn)
    record={'mode':'single-allocation','repeat_scope':'within-allocation-round',
            'job_id':os.environ['SLURM_JOB_ID'],'hosts':hosts,'configuration':config,'steps':steps,'status':'running'}
    plan=dest/'allocation-plan.json'
    if plan.exists(): raise ValueError('Plan already exists; use a new campaign')
    def save():
        temporary=dest/'allocation-plan.json.tmp'
        temporary.write_text(json.dumps(record,indent=2)+'\n'); temporary.replace(plan)
    save()
    pending=[]
    def launch(step):
        env=os.environ.copy()
        env.update(TRIAL_SELECTED_HOSTS=','.join(step['hosts']),TRIAL_EXPECTED_NODES=str(step['nodes']),
                   RANKS_PER_NODE=str(step['rpn']),TRIAL_REPLICATE_ID=str(step['round']),TRIAL_RUN_LABEL=step['label'],
                   TRIAL_ALLOCATION_MODE='single-allocation',TRIAL_REPEAT_SCOPE='within-allocation-round')
        command=['/bin/bash',str(root/'reframe/allocation-worker.sh'),step['phase']]
        if step['phase'].startswith('serial-'):
            command=[str(slurm/'srun'),'--exact','--export=ALL','--nodes=1','--ntasks=1',
                     '--ntasks-per-node=1','--cpus-per-task=4','--cpu-bind=cores',
                     '--nodelist='+env['TRIAL_SELECTED_HOSTS'],*command]
        step['status']='running'; step['started_utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()); save()
        log=(dest/(step['label']+'.log')).open('w')
        try: proc=subprocess.Popen(command,env=env,stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True)
        except BaseException: log.close(); raise
        pending.append((step,proc,log))
    def finish():
        failed=[]
        for step,proc,log in pending:
            code=proc.wait(); log.close()
            step.update(status='passed' if code==0 else 'failed',exit_code=code,
                        finished_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())); save()
            if code: failed.append(step['label'])
        pending.clear()
        if failed: raise RuntimeError('Failed steps: '+','.join(failed))
    def interrupted(signum,frame): raise KeyboardInterrupt(f'Signal {signum}')
    signal.signal(signal.SIGTERM,interrupted)
    try:
        # Inventory finishes before timers start; MPI does not run inside this step.
        subprocess.run([str(slurm/'srun'),'--exact','--export=ALL',f'--nodes={len(hosts)}',f'--ntasks={len(hosts)}',
                        '--ntasks-per-node=1','--cpus-per-task=1','/bin/bash',
                        str(root/'reframe/inspect-node.sh'),'mpi-strong',str(dest)],check=True)
        for step in steps:
            if step['status']=='skipped_capacity': continue
            parallel=step['phase']=='serial-cpu' and bool(config['TRIAL_CPU_PARALLEL'])
            if not parallel: finish()
            launch(step)
            if not parallel: finish()
        finish()
        record['status']='finished_with_capacity_skips' if any(s['status']=='skipped_capacity' for s in steps) else 'finished_steps'
    except BaseException as error:
        record['status']='failed_or_interrupted'; record['error']=str(error)
        raise
    finally:
        for step,proc,log in pending:
            if proc.poll() is None:
                try: os.killpg(proc.pid,signal.SIGTERM)
                except ProcessLookupError: pass
                try: proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    try: os.killpg(proc.pid,signal.SIGKILL)
                    except ProcessLookupError: pass
                    proc.wait()
            log.close()
            if step['status']=='running': step.update(status='interrupted',exit_code=proc.returncode)
        for step in steps:
            if step['status']=='pending': step['status']='not_run_after_failure'
        save()
    print(f'Finished available steps; inspect coverage/reports: {plan}')
    return 0

if __name__=='__main__':
    sys.exit(main())
PY
```

## 5. Submit one allocation

The wrapper uses the site's master modules and explicit trial environment. It requests four task slots per node and defaults to exclusive nodes. It records the submission settings and one job in `jobs.tsv`, which the existing collector/accounting commands can use.

```bash
cat > "$TRIAL_ROOT/reframe/submit-allocation.sh" <<'SH'
#!/bin/bash
set -euo pipefail
source "${TRIAL_MODULE_SETUP:?}"
source "$TRIAL_ROOT/env.sh"
test "${HARDENING_SET:-listed}" = listed
export TRIAL_ALLOCATION_NODES=${TRIAL_ALLOCATION_NODES:-8}
export TRIAL_ROUNDS=${TRIAL_ROUNDS:-3} PAIRS=${PAIRS:-20}
export TRIAL_CPU_PARALLEL=${TRIAL_CPU_PARALLEL:-1} RUN_WEAK=${RUN_WEAK:-0}
export NODE_COUNTS=${NODE_COUNTS:-'1 2 4 8'} RANK_LAYOUTS=${RANK_LAYOUTS:-1}
export CAMPAIGN_COMPARATORS=${CAMPAIGN_COMPARATORS:-reference}
export TRIAL_SCOPE=${TRIAL_SCOPE:-stack} RUN_PIE=${RUN_PIE:-0}
export TRIAL_EXCLUSIVE=${TRIAL_EXCLUSIVE:-1}
export CAMPAIGN_ID="single-$(date -u +%Y%m%dT%H%M%SZ)-$$"
dest="$TRIAL_ROOT/results/campaigns/$CAMPAIGN_ID"
mkdir -p "$dest"
python3 "$TRIAL_ROOT/reframe/allocation-controller.py" --validate > "$dest/validated-config.json"
python3 - "$dest/inputs.json" <<'PY'
import json, os, pathlib, sys
names=('CAMPAIGN_ID','TRIAL_ALLOCATION_NODES','TRIAL_ROUNDS','PAIRS','TRIAL_CPU_PARALLEL',
       'NODE_COUNTS','RANK_LAYOUTS','RUN_WEAK','CAMPAIGN_COMPARATORS','TRIAL_SCOPE','RUN_PIE','TRIAL_PROCEDURE_COMMIT','TRIAL_EXCLUSIVE',
       'TRIAL_WALLTIME','TRIAL_REGRESSION_LIMIT_PERCENT','SLURM_ACCOUNT','SLURM_PARTITION',
       'SLURM_CONSTRAINT','TRIAL_MODULE_SETUP','TRIAL_MPI_TUNING','SHARED_IO_DIR','TRIAL_LOCAL_IO_DIR',
       'MPI_GLOBAL_ELEMENTS','MPI_GLOBAL_SMALL_ELEMENTS','MPI_ELEMENTS_PER_RANK','MPI_SMALL_ELEMENTS_PER_RANK')
pathlib.Path(sys.argv[1]).write_text(json.dumps({n:os.environ.get(n,'') for n in names},indent=2)+'\n')
PY
options=(--parsable --account="${SLURM_ACCOUNT:?}" --partition="${SLURM_PARTITION:?}"
         --time="${TRIAL_WALLTIME:?}" --export=ALL --chdir="$TRIAL_ROOT"
         --nodes="$TRIAL_ALLOCATION_NODES" --ntasks="$((TRIAL_ALLOCATION_NODES*4))"
         --ntasks-per-node=4 --cpus-per-task=1 --job-name=hardening-single-allocation
         --output="$dest/%j.out" --error="$dest/%j.err")
if test -n "${SLURM_CONSTRAINT:-}"; then options+=(--constraint="$SLURM_CONSTRAINT"); fi
if test "$TRIAL_EXCLUSIVE" = 1; then options+=(--exclusive); fi
response=$("$SLURM_BINDIR/sbatch" "${options[@]}" "$TRIAL_ROOT/reframe/allocation-batch.sh")
id=${response%%;*}
[[ "$id" =~ ^[0-9]+$ ]]
printf 'job_id\tphase\tnodes\tranks_per_node\treplicate\n%s\tsingle-allocation\t%s\t4\t1\n' \
  "$id" "$TRIAL_ALLOCATION_NODES" > "$dest/jobs.tsv"
printf 'Campaign: %s\nJob: %s\nManifest: %s/jobs.tsv\n' "$CAMPAIGN_ID" "$id" "$dest"
SH
cat > "$TRIAL_ROOT/reframe/allocation-batch.sh" <<'SH'
#!/bin/bash
set -euo pipefail
source "$TRIAL_MODULE_SETUP"
source "$TRIAL_ROOT/env.sh"
exec python3 "$TRIAL_ROOT/reframe/allocation-controller.py"
SH
chmod +x "$TRIAL_ROOT/reframe/submit-allocation.sh" "$TRIAL_ROOT/reframe/allocation-batch.sh"
/bin/bash "$TRIAL_ROOT/reframe/submit-allocation.sh"
```

Do not modify generated scripts, binaries or settings while this job is queued/running. The job exits and releases its allocation when the fixed plan finishes; walltime is an upper bound, not a request to remain idle until it expires. A controller/worker failure stops further conditions; completed results and the plan remain. A time-limit kill can leave steps marked running/pending, so reconcile the plan with Slurm accounting and ReFrame reports. `finished_steps` means the workers returned successfully, not that every test or scale meets the performance limit.

## 6. Collect results and choose a fallback

Use [08 section 6](08-slurm-campaign.md#6-collect-and-interpret-every-phase) with the printed campaign ID. `phases.csv` uses `node_list` for the selected hosts and `allocated_node_list` for the whole allocation. It records `allocation_mode=single-allocation`, `repeat_scope=within-allocation-round`, round/replicate and step IDs where available. Actual MPI rank-to-host evidence remains in driver logs. Plot per-host/group/round estimates rather than pooling all pairs as independent allocations. Follow [09](09-results-presentation.md) for reporting.

If an eight-node request stays queued beyond your chosen wait budget, cancel that queued job through the site's normal `scancel JOB_ID`, then submit a **new campaign** with `TRIAL_ALLOCATION_NODES=4` or `2`. Leave larger scales in `NODE_COUNTS` to have them explicitly marked `skipped_capacity`, or preselect the smaller scope. The script does not silently resubmit or change running allocations. With two nodes, rotating rounds cannot supply another two-node set; record that limitation and use a later allocation for that check.

If node-subset steps or private MPI/Slurm integration cannot be qualified, use the unchanged separate-job submission route in 08. Its `ALLOCATION_REPEATS` requests new jobs; this mode's `TRIAL_ROUNDS` repeats inside one job. Keep those meanings distinct in reports. No system Slurm, MPI, UCX or compiler installation is changed by either mode.
