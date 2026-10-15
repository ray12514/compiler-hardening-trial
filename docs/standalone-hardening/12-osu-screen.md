# 12 — Small OSU communication screen

Use this with the complete-profile comparison in [11](11-stack-comparison.md). OSU Micro-Benchmarks is a separate suite, not bundled with Open MPI. The first screen compares **two matched bundles**, full Open MPI + full UCX versus reference Open MPI + reference UCX, with matching benchmark executable flags. It measures the combined scope; it cannot attribute the effect to MPI, UCX or the benchmark caller individually.

There is no package × MPI × UCX × flag Cartesian product. Keep only full/reference builds initially. A later MPI-only investigation uses identical benchmark binaries and fixed UCX, with verified compatible MPI libraries; define that separate scope before running.

## 1. Pin and build OSU 7.5.2

The pinned stable release is separate from the trial's existing package roster. The four selected C MPI tests are `osu_latency`, `osu_bw`, `osu_allreduce`, and `osu_alltoall`. Use `mpicc`/`mpicxx`; disabling Open MPI's legacy C++ bindings does not remove the C++ compiler wrapper. Stage on a connected machine and transfer the archive if needed. The checksum below was recomputed from the official archive. [Official download and benchmark descriptions](https://mvapich.cse.ohio-state.edu/benchmarks/), [official README](https://mvapich.cse.ohio-state.edu/static/media/mvapich/README-OMB.txt).

```bash
source "$TRIAL_ROOT/env.sh"
source "$TRIAL_ROOT/profiles.sh"
cd "$TRIAL_ROOT/downloads"
curl -fL --retry 3 -o osu-micro-benchmarks-7.5.2.tar.gz \
  https://mvapich.cse.ohio-state.edu/download/mvapich/osu-micro-benchmarks-7.5.2.tar.gz
printf '%s\n' '618de3d0b1122f73a9229177d2da1e5cd62e431190580cb915f2605849cbbbdc  osu-micro-benchmarks-7.5.2.tar.gz' \
  > OSU-SHA256SUMS
sha256sum --check OSU-SHA256SUMS
tar -xf osu-micro-benchmarks-7.5.2.tar.gz -C "$TRIAL_ROOT/src"
OSU_VARIANTS=(full reference)
for p in "${OSU_VARIANTS[@]}"; do
    activate_mpi_profile "$p"
    profile_flags "$p"
    build="$TRIAL_ROOT/build/osu-$p"
    prefix="$TRIAL_ROOT/install/osu/$p"
    test ! -e "$build"
    test ! -e "$prefix"
    mkdir -p "$build" "$TRIAL_ROOT/logs/osu/$p"
    (
      cd "$build"
      CC="$MPI_PREFIX/bin/mpicc" CXX="$MPI_PREFIX/bin/mpicxx" \
        CFLAGS="$EXE_CFLAGS" CXXFLAGS="$EXE_CXXFLAGS" CPPFLAGS='' \
        LDFLAGS="$EXE_LDFLAGS" \
        "$TRIAL_ROOT/src/osu-micro-benchmarks-7.5.2/configure" --prefix="$prefix" \
        2>&1 | tee "$TRIAL_ROOT/logs/osu/$p/configure.log"
      make -j "$JOBS" V=1 2>&1 | tee "$TRIAL_ROOT/logs/osu/$p/build.log"
      make install 2>&1 | tee "$TRIAL_ROOT/logs/osu/$p/install.log"
      cp config.log "$TRIAL_ROOT/logs/osu/$p/config.log"
    )
    declare -p EXE_CFLAGS EXE_CXXFLAGS EXE_LDFLAGS MPI_PREFIX UCX_PREFIX \
      > "$TRIAL_ROOT/logs/osu/$p/flags.txt"
    for path in mpi/pt2pt/osu_latency mpi/pt2pt/osu_bw mpi/collective/osu_allreduce mpi/collective/osu_alltoall; do
        exe="$prefix/libexec/osu-micro-benchmarks/$path"
        test -x "$exe"
        readelf -hW "$exe" > "$TRIAL_ROOT/logs/osu/$p/$(basename "$exe").elf.txt"
        readelf -lW "$exe" >> "$TRIAL_ROOT/logs/osu/$p/$(basename "$exe").elf.txt"
        readelf -dW "$exe" >> "$TRIAL_ROOT/logs/osu/$p/$(basename "$exe").elf.txt"
    done
done
source "$TRIAL_ROOT/mpi-env.sh"
```

Inspect the requested flags, ELF controls and loaded MPI. OSU's measured targets here are executables: use PIE flags, not a shared-library `-pie` injection. Qualification below validates the two selected collectives with `--validation` outside the timed sample series. Latency/bandwidth tests are transport probes, not a complete MPI correctness suite; retain 00b's transport/collective qualification and package correctness tests.

## 2. Predeclare the small matrix

| Test | Message bytes | Initial placement | Report |
|---|---|---|---|
| `osu_latency` | 1, 1,024, 65,536 | Two nodes, one rank/node | One-way latency, microseconds |
| `osu_bw` | 1,024, 65,536, 1,048,576 | Two nodes, one rank/node | Unidirectional bandwidth, MB/s |
| `osu_allreduce` | 16, 1,024, 65,536 | Same two nodes, one rank/node | Average collective latency, microseconds |
| `osu_alltoall` | 16, 1,024, 65,536 | Same two nodes, one rank/node | Average collective latency, microseconds |

This is **12 paired comparisons per allocation**, using two benchmark builds. Small-message/high-call-rate paths may expose CPU overhead; network-bound bulk transfers may dilute it. These are hypotheses, not predicted percentages. Two-rank all-to-all is a screen, not a realistic many-rank FFT exchange. Add a separately labelled four-ranks/node collective lane or 4/8-node follow-up when the application or screen warrants it. Do not run the two-rank point-to-point benchmarks with extra ranks.

Start with 10 process pairs in one allocation for qualification. After inspecting noise/duration, predeclare the assessment's budget (starting point: 20 pairs in each of three allocations, with more than one homogeneous node set where possible). `-x` warms each OSU invocation; `-i` controls its measured internal iterations. Neither internal iterations nor ranks are independent process samples. Keep per-allocation estimates separate as in 08. Timed validation, verbose transport logging and concurrent workloads are disabled. Keep transport/device, affinity and OSU options identical across arms.

## 3. Generate the paired native-metric driver

Generate the rank guard in 11 first. It verifies library selection on every rank before OSU begins its timing and reports rank/host evidence. This driver rejects missing placement, missing/duplicate rows, nonfinite/zero metrics, wrong units and failed collective validation. It preserves raw OSU output and one native-unit observation per process arm. Bandwidth remains MB/s; its loss is computed as `100 * (1 - full/reference)`. Latency increase is `100 * (full/reference - 1)`. Positive values mean deterioration in either case.

```bash
cat > "$TRIAL_ROOT/bench/osu-paired.py" <<'PY'
import csv, hashlib, json, math, os, pathlib, random, re, shlex, statistics, subprocess, sys
root=pathlib.Path(os.environ['TRIAL_ROOT'])
name,size=sys.argv[1],int(sys.argv[2])
if name not in ('osu_latency','osu_bw','osu_allreduce','osu_alltoall') or size<1:
    raise SystemExit('Unsupported OSU case')
pairs=int(os.environ.get('PAIRS','10'))
nodes=int(os.environ['TRIAL_EXPECTED_NODES'])
rpn=int(os.environ['RANKS_PER_NODE']); ranks=int(os.environ['MPI_NP'])
iterations=int(os.environ.get('OSU_ITERATIONS','1000'))
warmups=int(os.environ.get('OSU_WARMUPS','100'))
if pairs<2 or nodes<2 or rpn<1 or ranks!=nodes*rpn or iterations<1 or warmups<1:
    raise SystemExit('Invalid pair/placement/iteration budget')
if name in ('osu_latency','osu_bw') and ranks!=2:
    raise SystemExit('Point-to-point screen requires exactly two ranks')
bandwidth=name=='osu_bw'; unit='MB/s' if bandwidth else 'us'
kind='pt2pt' if name in ('osu_latency','osu_bw') else 'collective'
out=root/'results/reframe'/os.environ['RUN_ID']/'osu'/name/str(size)
out.mkdir(parents=True,exist_ok=False)
configs={}
for arm,suffix in (('full','fixed'),('reference','reference')):
    mpi=root/'install'/f'openmpi-4.1.8-ucx-{suffix}'
    ucx=root/'install'/f'ucx-1.16.0-{suffix}'
    exe=root/'install/osu'/arm/'libexec/osu-micro-benchmarks/mpi'/kind/name
    if not exe.is_file() or not (mpi/'bin/mpirun').is_file():
        raise SystemExit('Missing OSU/MPI build')
    env=os.environ.copy()
    env.update(PATH=f'{mpi}/bin:{ucx}/bin:'+os.environ['PATH'],
               LD_LIBRARY_PATH=':'.join(x for x in (str(mpi/'lib'),str(ucx/'lib'),
                 os.environ['GCC_LIB_DIRS'],os.environ.get('TRIAL_SITE_LIB_DIRS','')) if x),
               TRIAL_MPI_PREFIX=str(mpi),TRIAL_UCX_PREFIX=str(ucx),TRIAL_LIBRARY_PREFIX='',
               OMPI_MCA_mca_base_component_path=str(mpi/'lib/openmpi'))
    env.pop('UCX_LOG_LEVEL',None)
    cmd=[str(mpi/'bin/mpirun'),'-np',str(ranks),'--map-by',os.environ['MPI_MAP'],
         '--bind-to','core','--mca','pml','ucx','--mca','btl','^uct']
    for variable in ('PATH','LD_LIBRARY_PATH','TRIAL_MPI_PREFIX','TRIAL_UCX_PREFIX',
                     'TRIAL_LIBRARY_PREFIX','OMPI_MCA_mca_base_component_path',
                     'OMPI_MCA_plm','OMPI_MCA_ras','UCX_TLS','UCX_NET_DEVICES'):
        if variable in env: cmd+=['-x',variable]
    cmd+=shlex.split(os.environ.get('MPI_EXTRA_ARGS',''))
    cmd+=['/bin/bash',str(root/'bench/rank-exec.sh'),str(exe),
          '-m',f'{size}:{size}','-x',str(warmups),'-i',str(iterations)]
    configs[arm]=(cmd,env)
def execute(arm,label,validate=False):
    cmd,env=configs[arm]
    proc=subprocess.run(cmd+(['--validation'] if validate else []),env=env,text=True,capture_output=True)
    (out/f'{label}-{arm}.stdout').write_text(proc.stdout)
    (out/f'{label}-{arm}.stderr').write_text(proc.stderr)
    proc.check_returncode()
    placement=re.findall(r'TRIAL_RANK rank=(\d+) host=(\S+)',proc.stderr)
    hosts=[h.split('.')[0] for _,h in placement]
    if len(placement)!=ranks or {int(r) for r,_ in placement}!=set(range(ranks)):
        raise RuntimeError('Missing/duplicate rank evidence')
    if len(set(hosts))!=nodes or any(hosts.count(h)!=rpn for h in set(hosts)):
        raise RuntimeError('Incorrect OSU rank placement')
    selected=os.environ.get('TRIAL_SELECTED_HOSTS','')
    if selected and set(hosts)!={h.split('.')[0] for h in selected.split(',')}:
        raise RuntimeError('Wrong selected hosts')
    header='Bandwidth (MB/s)' if bandwidth else 'Latency'
    if header not in proc.stdout or (not bandwidth and 'us' not in proc.stdout):
        raise RuntimeError('Unexpected OSU metric/header')
    rows=[line.split() for line in proc.stdout.splitlines() if re.match(r'^\s*\d+\s',line)]
    if len(rows)!=1 or int(rows[0][0])!=size:
        raise RuntimeError('Unexpected OSU message rows')
    value=float(rows[0][1])
    if not math.isfinite(value) or value<=0: raise RuntimeError('Invalid OSU metric')
    if validate and (rows[0][-1].lower()!='pass' or 'fail' in proc.stdout.lower()):
        raise RuntimeError('OSU collective validation failed')
    return value
for arm in configs:
    if kind=='collective': execute(arm,'validation',True)
    execute(arm,'warmup')
data=[]
with (out/'raw.csv').open('w',newline='') as handle:
    writer=csv.writer(handle);writer.writerow(['pair','order','benchmark','bytes','arm','value','unit'])
    for pair in range(pairs):
        values={}
        for order,arm in enumerate(('full','reference') if pair%2==0 else ('reference','full')):
            values[arm]=execute(arm,f'pair-{pair}')
            writer.writerow([pair,order,name,size,arm,values[arm],unit]);handle.flush()
        data.append(values)
logs=[math.log(d['full']/d['reference']) for d in data]
ratio=math.exp(statistics.mean(logs));rng=random.Random(20261009)
samples=sorted(math.exp(statistics.mean(rng.choices(logs,k=pairs))) for _ in range(10000))
change=lambda r:100*(1-r) if bandwidth else 100*(r-1)
interval=sorted((change(samples[250]),change(samples[9749])))
record={'benchmark':name,'bytes':size,'unit':unit,'scope':'stack','pairs':pairs,
        'full_value':math.exp(statistics.mean(math.log(d['full']) for d in data)),
        'reference_value':math.exp(statistics.mean(math.log(d['reference']) for d in data)),
        'full_mean':statistics.mean(d['full'] for d in data),
        'reference_mean':statistics.mean(d['reference'] for d in data),
        'full_stdev':statistics.stdev(d['full'] for d in data),
        'reference_stdev':statistics.stdev(d['reference'] for d in data),
        'deterioration_percent':change(ratio),'interval':interval,
        'commands_by_arm':{a:c[0] for a,c in configs.items()},
        'procedure_commit':os.environ.get('TRIAL_PROCEDURE_COMMIT',''),
        'executable_sha256_by_arm':{a:hashlib.sha256(pathlib.Path(c[0][c[0].index('/bin/bash')+2]).read_bytes()).hexdigest() for a,c in configs.items()},
        'context':{k:os.environ.get(k,'') for k in ('RUN_ID','CAMPAIGN_ID','SLURM_JOB_ID',
             'SLURM_JOB_NODELIST','TRIAL_REPLICATE_ID','TRIAL_EXPECTED_NODES','RANKS_PER_NODE',
             'MPI_NP','MPI_MAP','UCX_TLS','UCX_NET_DEVICES','OSU_ITERATIONS','OSU_WARMUPS')},
        'hardening_set':os.environ.get('HARDENING_SET','listed')}
(out/'summary.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record,indent=2))
PY
```

## 4. ReFrame output inside Slurm

Use the allocation-local settings and private ReFrame installation from 06. This is a separate OSU check file; the package check file and its `phases.csv` collector remain available. OSU keeps native-unit `raw.csv`/`summary.json` in the same session tree, and ReFrame reports actual us/MB/s units. Do not feed these native metrics to the package runtime collector.

```bash
cat > "$TRIAL_ROOT/reframe/osu.py" <<'PY'
import json, os, pathlib, shlex
import reframe as rfm
import reframe.utility.sanity as sn
from reframe.core.builtins import parameter, run_before, sanity_function, performance_function
ROOT=pathlib.Path(os.environ['TRIAL_ROOT'])
@sn.deferrable
def result(stdout,key,index=None):
    value=json.loads(pathlib.Path(stdout).read_text())[key]
    return value if index is None else value[index]
class OSUScreen(rfm.RunOnlyRegressionTest):
    valid_systems=['hardening:allocation'];valid_prog_environs=['gcc125']
    sourcesdir=None;time_limit='30m'
    @run_before('run')
    def prepare(self):
        name,size=self.case
        self.descr=f'{name}, {size} bytes: complete full/reference stack'
        self.tags={'hardening','mpi','osu','stack'}
        self.env_vars={n:shlex.quote(os.environ[n]) for n in (
            'TRIAL_ROOT','GCC_LIB_DIRS','RUN_ID','PAIRS','TRIAL_EXPECTED_NODES',
            'RANKS_PER_NODE','MPI_NP','MPI_MAP')}
        for name in ('TRIAL_SITE_LIB_DIRS','MPI_EXTRA_ARGS','UCX_TLS','UCX_NET_DEVICES',
                     'OMPI_MCA_plm','OMPI_MCA_ras','CAMPAIGN_ID','TRIAL_REPLICATE_ID',
                     'TRIAL_PROCEDURE_COMMIT','TRIAL_SELECTED_HOSTS','OSU_ITERATIONS','OSU_WARMUPS','HARDENING_SET'):
            if name in os.environ:self.env_vars[name]=shlex.quote(os.environ[name])
        self.executable='python3'
        self.executable_opts=[shlex.quote(str(x)) for x in
            (ROOT/'bench/osu-paired.py',self.case[0],size)]
    @sanity_function
    def completed(self):
        return sn.all([sn.assert_eq(self.job.exitcode,0),
                       sn.assert_found(r'"deterioration_percent"',self.stdout)])
    @performance_function('%')
    def deterioration(self):return result(self.stdout,'deterioration_percent')
    @performance_function('%')
    def interval_low(self):return result(self.stdout,'interval',0)
    @performance_function('%')
    def interval_high(self):return result(self.stdout,'interval',1)
@rfm.simple_test
class OSULatencyScreen(OSUScreen):
    case=parameter([(n,s) for n,sizes in (
        ('osu_latency',(1,1024,65536)),('osu_allreduce',(16,1024,65536)),
        ('osu_alltoall',(16,1024,65536))) for s in sizes])
    @performance_function('us')
    def full_value(self):return result(self.stdout,'full_value')
    @performance_function('us')
    def reference_value(self):return result(self.stdout,'reference_value')
@rfm.simple_test
class OSUBandwidthScreen(OSUScreen):
    case=parameter([('osu_bw',s) for s in (1024,65536,1048576)])
    @performance_function('MB/s')
    def full_value(self):return result(self.stdout,'full_value')
    @performance_function('MB/s')
    def reference_value(self):return result(self.stdout,'reference_value')
PY
# Obtain two nodes through the site's normal account/partition route first:
# salloc --account=YOUR_ACCOUNT --partition=YOUR_PARTITION -N 2 --ntasks-per-node=1 -t 01:00:00
source "$TRIAL_ROOT/mpi-env.sh"
# Reapply the qualified site UCX tuning file here, if one is used.
unset UCX_LOG_LEVEL
export MPI_NP=2 MPI_MAP=ppr:1:node TRIAL_EXPECTED_NODES=2 RANKS_PER_NODE=1
export PAIRS=10 OSU_ITERATIONS=1000 OSU_WARMUPS=100
export RUN_ID="osu-$(date -u +%Y%m%dT%H%M%SZ)-$$"
export REFRAME="$TRIAL_ROOT/tools/reframe-venv/bin/reframe"
mkdir -p "$TRIAL_ROOT/results/reframe/$RUN_ID"
"$REFRAME" -C "$TRIAL_ROOT/reframe/settings.py" -c "$TRIAL_ROOT/reframe/osu.py" -l
"$REFRAME" -C "$TRIAL_ROOT/reframe/settings.py" -c "$TRIAL_ROOT/reframe/osu.py" \
  -r --exec-policy=serial --performance-report \
  --prefix="$TRIAL_ROOT/results/reframe/$RUN_ID/rfm" \
  --report-file="$TRIAL_ROOT/results/reframe/$RUN_ID/report.json" \
  2>&1 | tee "$TRIAL_ROOT/results/reframe/$RUN_ID/console.log"
```

Run the same fixed assessment in each newly obtained allocation with a fresh `RUN_ID` and recorded replicate/node set. List the checks before running; select latency/collective checks explicitly when trying a denser collective placement. Record all completed and failed comparisons, not only favorable message sizes. PASS means validation/placement/measurement completed, not that the slowdown meets a policy threshold.

Present native latency/bandwidth alongside deterioration percentages and intervals. Keep OSU results separate from FFTW/HDF5/LAPACK kernels, label scope `stack`, and use the plots/reporting approach in 09 with real measured values. Transport, algorithm selection, rank density and message size are part of each finding's scope. Expand individual flags only after the combined screen warrants it.
