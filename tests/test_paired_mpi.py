"""Execute the real paired harness through fixture MPI launchers and dependencies."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from test_mpi_driver import driver_at, executable


class PairedMpiTests(unittest.TestCase):
    def test_both_timing_arms_use_qualified_components_overlap_and_private_stacks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            driver = driver_at(root)
            (root/'bench').mkdir()
            tools = root/'tools'
            executable(tools/'ldd', '''IFS=: read -r payload mpi ucx rest <<< "$LD_LIBRARY_PATH"
printf 'libhdf5.so => %s/libhdf5.so\nlibmpi.so => %s/libmpi.so\nlibucp.so => %s/libucp.so\n' "$payload" "$mpi" "$ucx"
''')
            for arm, suffix in (('full','fixed'),('reference','reference')):
                (root/'install/hdf5-mpi'/arm/'lib').mkdir(parents=True)
                (root/'install'/f'ucx-1.16.0-{suffix}'/'lib').mkdir(parents=True)
                mpi = root/'install'/f'openmpi-4.1.8-ucx-{suffix}'
                executable(mpi/'bin/mpirun', '''python3 - "$@" <<'CODE'
import os,subprocess,sys
args=sys.argv[1:]
for name,value in [('btl','^uct,openib,ofi'),('mtl','^ofi'),('plm_slurm_args','--overlap')]:
    assert args.count(name)==1,(name,args)
    assert args[args.index(name)+1]==value,(name,args)
assert 'UCX_PREFIX' not in os.environ
assert 'UCX_LOG_LEVEL' not in os.environ
assert os.environ['UCX_TLS']=='rc,sm,self'
index=args.index('/bin/bash')+2
for rank in range(8): print(f'MPI_PLACEMENT rank={rank} host=node{1+rank//4}',file=sys.stderr)
print('MPI_PLACEMENT nodes=2 ranks=8',file=sys.stderr)
sys.exit(subprocess.run(args[index:]).returncode)
CODE
''')
                executable(root/'bench'/f'hdf5-mpi-{suffix}',
                           "echo 'write_collective_maxrank," + ('1.2' if arm=='full' else '1.0') + ",0'\n")
            env = {**os.environ, 'TRIAL_ROOT': str(root), 'PATH': str(tools)+':'+os.environ['PATH'],
                   'TRIAL_SCOPE': 'stack', 'COMPARE': 'reference', 'PAIRS': '2', 'MPI_NP': '8',
                   'MPI_MAP': 'ppr:4:node', 'TRIAL_EXPECTED_NODES': '2', 'RANKS_PER_NODE': '4',
                   'TRIAL_SELECTED_HOSTS': 'node1,node2', 'GCC_LIB_DIRS': '/gcc/lib', 'OMPI_MCA_io': 'romio321',
                   'OMPI_MCA_btl': '^uct,openib,ofi', 'OMPI_MCA_mtl': '^ofi', 'OMPI_MCA_plm': 'slurm',
                   'OMPI_MCA_ras': 'slurm', 'OMPI_MCA_plm_slurm_args': '--overlap', 'UCX_TLS': 'rc,sm,self',
                   'UCX_PREFIX': '/shell-only-path', 'UCX_LOG_LEVEL': 'info',
                   'COMPARE_EXECUTABLE': str(root/'bench/hdf5-mpi-reference'),
                   'PRIMARY_PHASE': 'write_collective_maxrank'}
            subprocess.run(['bash','-c',driver.block('01-common',4)],env=env,check=True)
            result = subprocess.run([sys.executable,str(root/'bench/paired.py'),'hdf5-mpi',
                                     str(root/'bench/hdf5-mpi-fixed'),'pilot'],env=env,
                                    capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stderr)
            summary = json.loads(result.stdout)
            self.assertAlmostEqual(summary['phases']['write_collective_maxrank']['full_runtime_increase_percent'],20.0)
            self.assertEqual(summary['context']['OMPI_MCA_plm_slurm_args'],'--overlap')
            self.assertEqual(set(summary['launcher_by_arm']),{'full','reference'})


if __name__ == '__main__':
    unittest.main()
