# 06 — Drive the hardening trial with ReFrame

**Normal route:** follow the [README](README.md), prepare ReFrame with `"$TRIAL_ROOT/runner/trial" prepare-tests` on the login node, then run `"$TRIAL_ROOT/runner/trial" test fftw` in the compute allocation. The driver runs the applicable blocks below in child shells, including prerequisites. These numbered sections are recipe references; do not paste all of them after using the driver.

ReFrame drives the tests against the already-built package variants. It runs the paired timing harness from [01](01-common.md), checks that the measurements completed correctly, extracts runtimes and changes, and prints a performance table. Raw paired CSV, driver logs, loaded-library records, and JSON summaries are preserved. It does not need Spack.

The configuration below runs locally **inside an existing scheduler allocation**. Serial checks constrain the caller to `CPUSET`; parallel checks use matching Open MPI + UCX launchers in stack scope, or the fixed full launcher in library scope, with identical mapping. This keeps paired runs on the same allocation instead of submitting a different allocation for each hardening arm. Use ReFrame's serial execution policy so workloads do not compete for CPUs or the test filesystem.

[08 — Slurm campaign](08-slurm-campaign.md) defines the hypotheses, expanded workload matrix, 1/2/4/8-node sequence, batch submission, placement checks, and collection of all phase results. The interactive commands below remain a small pilot. ReFrame drives prebuilt variants; the campaign does not build packages during timing.

## 1. Install a pinned ReFrame in a private environment

Python 3.10 or later is required. Install on a connected login node into the shared trial path **before** compute-node testing. The driver command `prepare-tests` runs this installation recipe explicitly; `test` only checks readiness and never installs. ReFrame preparation does not rebuild GCC or payloads. Use a compatible base Python available at the same absolute path on login and compute nodes. No Python libraries are installed into the system environment.

```bash
source "$TRIAL_ROOT/env.sh"
python3 -m venv "$TRIAL_ROOT/tools/reframe-venv"
"$TRIAL_ROOT/tools/reframe-venv/bin/python" -m pip install 'reframe-hpc==4.10.4'
export REFRAME="$TRIAL_ROOT/tools/reframe-venv/bin/reframe"
"$REFRAME" --version
```

Offline alternative on the staging host: `python3 -m pip download --only-binary=:all: 'reframe-hpc==4.10.4' -d /path/to/wheels`, using a host with the same Python ABI, OS and architecture as the test system. The README gives the complete `prepare-tests --wheelhouse DIR` route. Transfer all dependency wheels, then use `pip install --no-index --find-links=/path/to/wheels 'reframe-hpc==4.10.4'` inside the private environment. Retain the package/version list with the results. See [ReFrame 4.10.4](https://pypi.org/project/reframe-hpc/4.10.4/) and the [official tutorial](https://reframe-hpc.readthedocs.io/en/stable/tutorial.html).

## 2. Create the allocation-local configuration

```bash
mkdir -p "$TRIAL_ROOT/reframe" "$TRIAL_ROOT/results/reframe"
cat > "$TRIAL_ROOT/reframe/settings.py" <<'PY'
import os
root = os.environ['TRIAL_ROOT']
site_configuration = {
    'systems': [{
        'name': 'hardening', 'descr': 'Standalone GCC 12.5 trial allocation',
        'hostnames': ['.*'],
        'partitions': [{
            'name': 'allocation', 'scheduler': 'local', 'launcher': 'local',
            'environs': ['gcc125']
        }]
    }],
    'general': [{'topology_prefix': root + '/reframe/topology'}],
    'environments': [{
        'name': 'gcc125',
        'cc': root + '/toolchains/gcc-12.5.0/bin/gcc',
        'cxx': root + '/toolchains/gcc-12.5.0/bin/g++',
        'ftn': root + '/toolchains/gcc-12.5.0/bin/gfortran'
    }]
}
PY
```

The environment names the compiler for provenance. These are run-only checks; the configuration does not build GCC or replace the compiler selected by the build runbooks.

## 3. Create the test definition

[11](11-stack-comparison.md) selects `TRIAL_SCOPE=stack` for the primary complete-profile comparison and builds reference callers. That mode changes the caller, package, matching MPI/UCX and reference-implementation BLAS together. `TRIAL_SCOPE=library` retains one full caller, full MPI/UCX and full BLAS for package attribution. The default here remains library scope so manual package commands retain that meaning. Explicitly select and record scope for every campaign. These are operator-driven Slurm runs outside CI.


Initially `COMPARATORS=reference`. After installing selected listed-set removals, use e.g. `COMPARATORS=reference,minus-stack,minus-fortify,minus-relro,minus-now`. ReFrame expands the workload/comparator combinations. `minus-fortify` is skipped for Fortran LAPACK; the extended set also skips `minus-init` for LAPACK. Use [07](07-consumer-pie.md) for the executable PIE comparison.

The primary HDF5 metric shown in the table is write/create/close. Read timing is retained in each summary and raw CSV. FFTW's primary metric is execution; planning is retained separately. One full/comparator check includes the warmups and all `PAIRS` fresh process pairs within the same allocation. Kernel iterations within a process and MPI ranks are not additional statistical samples. Arithmetic means and sample standard deviations are retained in summaries; the terminal's headline remains the paired geometric mean and its interval.

```bash
cat > "$TRIAL_ROOT/reframe/hardening.py" <<'PY'
import json
import os
import pathlib
import shlex
import reframe as rfm
import reframe.utility.sanity as sn
from reframe.core.builtins import parameter, run_after, run_before
from reframe.core.builtins import sanity_function, performance_function

ROOT = pathlib.Path(os.environ['TRIAL_ROOT'])
SCOPE = os.environ.get('TRIAL_SCOPE', 'library')
if SCOPE not in ('library','stack'): raise ValueError('Invalid TRIAL_SCOPE')
WORKLOADS = {
    'fft-small': ('fftw', 'fftw-fixed', 'execution', ['1','1024','50000','1','estimate'], False),
    'fft-large': ('fftw', 'fftw-fixed', 'execution', ['1','1048576','30','1','estimate'], False),
    'fft-3d': ('fftw', 'fftw-fixed', 'execution', ['3','64','100','1','estimate'], False),
    'fft-plan': ('fftw', 'fftw-fixed', 'planning', ['3','64','1','1','measure'], False),
    'fft-threads': ('fftw', 'fftw-fixed', 'execution', ['1','1048576','30','@THREADS@','estimate'], False),
    'hdf5-contiguous': ('hdf5', 'hdf5-fixed', 'write_create_close', ['@FILE@','16777216','0','0'], False),
    'hdf5-chunked': ('hdf5', 'hdf5-fixed', 'write_create_close', ['@FILE@','16777216','65536','0'], False),
    'hdf5-small': ('hdf5', 'hdf5-fixed', 'write_create_close', ['@FILE@','8192','0','0'], False),
    'hdf5-metadata': ('hdf5', 'hdf5-fixed', 'write_create_close', ['@FILE@','128','0','0','1000'], False),
    'lapack-small': ('lapack', 'lapack-fixed', 'lu_solve', ['128','50'], False),
    'lapack-large': ('lapack', 'lapack-fixed', 'lu_solve', ['1024','3'], False),
    'fft-startup': ('fftw', 'fftw-fixed', 'process_elapsed', ['1','1024','100','1','estimate'], False),
    'hdf5-startup': ('hdf5', 'hdf5-fixed', 'process_elapsed', ['@FILE@','128','0','0'], False),
    'lapack-startup': ('lapack', 'lapack-fixed', 'process_elapsed', ['128','1'], False),
    'fft-pie': ('fftw', 'fftw-fixed', 'process_elapsed', ['1','1024','100','1','estimate'], False),
    'hdf5-pie': ('hdf5', 'hdf5-fixed', 'process_elapsed', ['@FILE@','128','0','0'], False),
    'lapack-pie': ('lapack', 'lapack-fixed', 'process_elapsed', ['128','1'], False),
    'fft-mpi': ('fftw-mpi', 'fftw-mpi-fixed', 'execution_maxrank', ['64','100','estimate'], True),
    'fft-mpi-small': ('fftw-mpi', 'fftw-mpi-fixed', 'execution_maxrank', ['32','200','estimate'], True),
    'fft-mpi-large': ('fftw-mpi', 'fftw-mpi-fixed', 'execution_maxrank', ['128','30','estimate'], True),
    'fft-mpi-plan': ('fftw-mpi', 'fftw-mpi-fixed', 'planning_maxrank', ['64','1','measure'], True),
    'hdf5-collective': ('hdf5-mpi', 'hdf5-mpi-fixed', 'write_collective_maxrank', ['@FILE@','@MPI_ELEMENTS@','collective'], True),
    'hdf5-independent': ('hdf5-mpi', 'hdf5-mpi-fixed', 'write_independent_maxrank', ['@FILE@','@MPI_ELEMENTS@','independent'], True),
    'hdf5-mpi-small': ('hdf5-mpi', 'hdf5-mpi-fixed', 'write_collective_maxrank', ['@FILE@','@MPI_SMALL_ELEMENTS@','collective'], True)
}
SELECTED = os.environ.get('WORKLOADS', 'fft-small,hdf5-contiguous,lapack-small').split(',')
COMPARATORS = os.environ.get('COMPARATORS', 'reference').split(',')
if any(w not in WORKLOADS for w in SELECTED):
    raise ValueError('Unknown WORKLOADS entry')

@sn.deferrable
def metric(stdout, phase, key, index=None):
    value = json.loads(pathlib.Path(stdout).read_text())['phases'][phase][key]
    return value if index is None else value[index]

@rfm.simple_test
class HardeningTrial(rfm.RunOnlyRegressionTest):
    workload = parameter(SELECTED)
    comparator = parameter(COMPARATORS)
    valid_systems = ['hardening:allocation']
    valid_prog_environs = ['gcc125']
    sourcesdir = None
    time_limit = '30m'

    @run_after('init')
    def describe(self):
        self.tags = {'hardening', SCOPE, 'mpi' if WORKLOADS[self.workload][4] else 'serial'}
        self.descr = f'{self.workload}: full vs {self.comparator}, {SCOPE} scope'

    @run_before('run')
    def prepare(self):
        package, driver, phase, arguments, mpi = WORKLOADS[self.workload]
        consumer = self.workload in ('fft-pie','hdf5-pie','lapack-pie')
        self.skip_if(SCOPE == 'stack' and consumer, 'PIE attribution is a separate library-scope follow-up')
        if SCOPE == 'stack' and self.comparator != 'reference':
            raise ValueError('Stack screening uses reference only')
        self.skip_if(consumer != (self.comparator == 'minus-pie'),
                     'PIE workloads require minus-pie; library workloads use library variants')
        self.skip_if(package == 'lapack' and self.comparator in ('minus-fortify','minus-init'),
                     'Control does not apply to Fortran LAPACK')
        session = os.environ['RUN_ID']
        io_dir = pathlib.Path(os.environ['IO_DIR'])
        if not io_dir.is_dir():
            raise ValueError('IO_DIR must be a dedicated existing trial directory')
        filename = io_dir / f'reframe-{self.workload}-{self.comparator}-{session}.h5'
        ranks = int(os.environ.get('MPI_NP','2')) if mpi else 0
        scaling = 'none'
        replacements = {'@FILE@': str(filename), '@THREADS@': os.environ.get('FFT_THREADS','4')}
        if mpi:
            if ranks<1:
                raise ValueError('MPI_NP must be positive')
            scaling = 'strong'
            if package == 'hdf5-mpi':
                scaling = os.environ.get('HDF5_SCALING_MODE','strong')
                if scaling not in ('strong','weak'):
                    raise ValueError('HDF5_SCALING_MODE must be strong or weak')
                for marker, global_name, rank_name, default_global, default_rank in (
                    ('@MPI_ELEMENTS@','MPI_GLOBAL_ELEMENTS','MPI_ELEMENTS_PER_RANK',16777216,8388608),
                    ('@MPI_SMALL_ELEMENTS@','MPI_GLOBAL_SMALL_ELEMENTS','MPI_SMALL_ELEMENTS_PER_RANK',8192,1024)):
                    total = int(os.environ.get(global_name,str(default_global)))
                    if scaling == 'strong' and (total<ranks or total%ranks):
                        raise ValueError('Global HDF5 elements must divide evenly across ranks')
                    count = total//ranks if scaling == 'strong' else int(os.environ.get(rank_name,str(default_rank)))
                    if not 1<=count<=33554432:
                        raise ValueError('Per-rank HDF5 size is outside caller limits')
                    replacements[marker] = str(count)
        arguments = [replacements.get(a,a) for a in arguments]
        self._phase = phase
        command = [str(ROOT/'bench'/'paired.py'), package,
                   str(ROOT/'bench'/driver), self.workload, *arguments]
        self.env_vars = {
            'TRIAL_ROOT': str(ROOT), 'GCC_LIB_DIRS': os.environ['GCC_LIB_DIRS'],
            'TRIAL_SITE_LIB_DIRS': os.environ.get('TRIAL_SITE_LIB_DIRS',''),
            'RESULT_ROOT': str(ROOT/'results'/'reframe'/session/'paired'),
            'COMPARE': self.comparator, 'PAIRS': os.environ.get('PAIRS','10'),
            'HARDENING_SET': os.environ.get('HARDENING_SET','listed'),
            'FORTIFY_LEVEL': os.environ.get('FORTIFY_LEVEL','2'),
            'TRIAL_SCOPE': SCOPE,
            'COMPARE_EXECUTABLE': str(ROOT/'bench'/f'{package}-reference') if SCOPE == 'stack'
                                  else str(ROOT/'bench'/f'{package}-minus-pie') if consumer else '',
            'MPI_NP': str(ranks), 'SCALING_MODE': scaling, 'IO_DIR': str(io_dir),
            'PRIMARY_PHASE': phase,
            'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1'
        }
        for name in ('TRIAL_PROCEDURE_COMMIT','CAMPAIGN_ID','TRIAL_RUN_LABEL','TRIAL_REPLICATE_ID','TRIAL_EXPECTED_NODES',
                     'RANKS_PER_NODE','CPUSET','THREAD_CPUSET','TRIAL_REGRESSION_LIMIT_PERCENT',
                     'TRIAL_SELECTED_HOSTS','TRIAL_ALLOCATION_MODE','TRIAL_REPEAT_SCOPE'):
            if name in os.environ:
                self.env_vars[name] = os.environ[name]
        if mpi:
            for name in ('MPI_PREFIX','MPI_LIB_DIRS','MPI_MAP','OMPI_MCA_io',
                         'OMPI_MCA_plm','OMPI_MCA_ras'):
                self.env_vars[name] = os.environ[name]
            for name in ('MPI_EXTRA_ARGS','UCX_TLS','UCX_NET_DEVICES','UCX_IB_GID_INDEX',
                         'UCX_IB_SL','UCX_IB_TRAFFIC_CLASS','OMPI_MCA_btl','OMPI_MCA_mtl',
                         'OMPI_MCA_plm_slurm_args'):
                if name in os.environ:
                    self.env_vars[name] = os.environ[name]
            self.executable = 'python3'
            self.executable_opts = [shlex.quote(arg) for arg in command]
        else:
            self.executable = 'taskset'
            cpuset = os.environ['THREAD_CPUSET'] if self.workload == 'fft-threads' else os.environ['CPUSET']
            self.executable_opts = [shlex.quote(arg) for arg in
                                    ['-c', cpuset, 'python3', *command]]
        # ReFrame emits these values into shell export statements.
        self.env_vars = {name: shlex.quote(value) for name,value in self.env_vars.items()}

    @sanity_function
    def measurements_completed(self):
        checks = [sn.assert_eq(self.job.exitcode, 0),
                  sn.assert_found(r'"runtime_ratio_full_over_comparator"', self.stdout)]
        limit = os.environ.get('MAX_SLOWDOWN_PERCENT')
        if limit is not None:
            checks.append(sn.assert_le(metric(self.stdout, self._phase,
                'bootstrap_95_percent_interval', 1), float(limit)))
        return sn.all(checks)

    @performance_function('s')
    def full_seconds(self):
        return metric(self.stdout, self._phase, 'full_runtime_seconds_geomean')

    @performance_function('s')
    def comparator_seconds(self):
        return metric(self.stdout, self._phase, 'comparator_runtime_seconds_geomean')

    @performance_function('%')
    def full_runtime_increase(self):
        return metric(self.stdout, self._phase, 'full_runtime_increase_percent')

    @performance_function('%')
    def interval_low(self):
        return metric(self.stdout, self._phase, 'bootstrap_95_percent_interval', 0)

    @performance_function('%')
    def interval_high(self):
        return metric(self.stdout, self._phase, 'bootstrap_95_percent_interval', 1)
PY
```

Without `MAX_SLOWDOWN_PERCENT`, PASS means the drivers' correctness checks and paired measurement procedure completed; it does not mean the overhead is acceptable. If an agreed limit is set, the sanity check also requires the upper interval bound of the primary metric to be below it. Do not use that same gate automatically for removal comparators: those show the incremental cost of a control, not total overhead versus reference.

## 4. List and run the serial pilot

Use a compute allocation and replace `CPUSET` with an allocated CPU. Set `IO_DIR` to a dedicated directory on the filesystem to measure. Use a new `RUN_ID` per ReFrame session; existing raw results are never overwritten.

```bash
source "$TRIAL_ROOT/env.sh"
export REFRAME="$TRIAL_ROOT/tools/reframe-venv/bin/reframe"
export CPUSET=0
export IO_DIR=/absolute/path/to/test-filesystem/hdf5-hardening-trial
mkdir -p "$IO_DIR"
export WORKLOADS=fft-small,hdf5-contiguous,lapack-small
export COMPARATORS=reference PAIRS=10
export RUN_ID
RUN_ID=$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$TRIAL_ROOT/results/reframe/$RUN_ID"
"$REFRAME" -C "$TRIAL_ROOT/reframe/settings.py" \
  -c "$TRIAL_ROOT/reframe/hardening.py" -l
"$REFRAME" -C "$TRIAL_ROOT/reframe/settings.py" \
  -c "$TRIAL_ROOT/reframe/hardening.py" -r --exec-policy=serial \
  --performance-report \
  --prefix="$TRIAL_ROOT/results/reframe/$RUN_ID/rfm" \
  --report-file="$TRIAL_ROOT/results/reframe/$RUN_ID/report.json" \
  2>&1 | tee "$TRIAL_ROOT/results/reframe/$RUN_ID/console.log"
```

The terminal shows each workload's PASS/FAIL and five metrics: full seconds, comparator seconds, full runtime increase %, and the interval endpoints. The actual values come from the run; this runbook contains no claimed benchmark results. ReFrame's JSON report retains its version/data-version and per-test performance values. The `paired/` subtree contains the CSV and summary JSON used to produce those numbers. See [ReFrame CLI/reporting](https://reframe-hpc.readthedocs.io/en/stable/manpage.html).

## 5. Drive parallel tests and the removal matrix

First build/qualify [Open MPI + UCX](00b-openmpi-ucx.md) and install the [parallel FFTW/HDF5 variants and fixed callers](05-parallel.md). Then, in the same two-node allocation:

```bash
source "$TRIAL_ROOT/mpi-env.sh"
export MPI_NP=2 MPI_MAP=ppr:1:node
export WORKLOADS=fft-mpi,hdf5-collective,hdf5-independent
export COMPARATORS=reference
export RUN_ID
RUN_ID=$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$TRIAL_ROOT/results/reframe/$RUN_ID"
"$REFRAME" -C "$TRIAL_ROOT/reframe/settings.py" \
  -c "$TRIAL_ROOT/reframe/hardening.py" -r --exec-policy=serial \
  --performance-report --prefix="$TRIAL_ROOT/results/reframe/$RUN_ID/rfm" \
  --report-file="$TRIAL_ROOT/results/reframe/$RUN_ID/report.json" \
  2>&1 | tee "$TRIAL_ROOT/results/reframe/$RUN_ID/console.log"
```

`IO_DIR` must be shared between those nodes. Rank binding is handled by Open MPI. Timed UCX logging stays off. To examine removals, install the selected variants first and change `COMPARATORS`, then run a new session with identical workloads and placement. A missing variant is a failed prerequisite, not a zero measurement.

This starter uses allocation-local execution deliberately. A later site configuration can use ReFrame's Slurm scheduler and MPI launcher directly, but paired arms must still share a controlled allocation/placement. Do not submit independent full/reference jobs to unrelated node types and treat their difference as compiler overhead.
