# Compiler hardening trial

Standalone procedures for measuring the correctness and runtime effects of
compiler hardening on FFTW, HDF5 and LAPACK, including parallel FFTW/HDF5 with
Open MPI and UCX.

The experiment uses GCC 12.5.0, Open MPI 4.1.8 and UCX 1.16.0. The runbooks
include toolchain bootstrap, flag qualification, direct source builds, matched
benchmark callers, paired measurements, ReFrame execution and Slurm campaigns.
Connected preparation and offline compute-node execution are documented.

Start with the [installation and trial workflow](docs/standalone-hardening/README.md).
Keep the checkout inside the trial working root as described there; build
artifacts and results live beside the checkout.

**Builds complete and MPI qualification passed?** Run the
[all-package pilot and CSV export](docs/standalone-hardening/README.md#builds-complete-and-mpi-qualified-run-the-package-pilot)
next, using the existing allocation.

Builds finished and already holding multiple nodes? Start with
[qualification in the existing allocation](docs/standalone-hardening/README.md#qualify-an-existing-multi-node-allocation-before-the-sweep)
before package pilots and the longer campaign.

Already building from the earlier Planning checkout? Use the
[existing trial handoff](docs/standalone-hardening/README.md#existing-trial-from-the-earlier-planning-checkout)
to keep the same environment, build state and results while switching sources.

- [Experiment design and measurement controls](docs/standalone_compiler_hardening_performance_trial_v1.md)
- [Published performance evidence and its limits](docs/standalone_compiler_hardening_performance_evidence_v1.md)
- [Interpreting and presenting results](docs/standalone-hardening/09-results-presentation.md)

Target-system GCC/package builds and campaign qualification remain outstanding.
The included reporting figures use illustrative data. Record the procedure
commit, source checksums, exact build identities and allocation conditions with
every actual result.

For the UCX optional Go-binding build failure, see the
[update and retry instructions](docs/standalone-hardening/README.md#if-ucx-stops-while-building-go-bindings).

For HDF5's `Could NOT find MFU` configure failure, use the
[parallel HDF5 update and retry steps](docs/standalone-hardening/README.md#if-parallel-hdf5-configuration-cannot-find-mfu).

For parallel `h5diff` output mismatches containing `UCX_PREFIX` warnings, use the
[runtime environment fix and continuation steps](docs/standalone-hardening/README.md#if-parallel-h5diff-tests-fail-with-ucx_prefix-warnings).

For MPI/PML errors or Mellanox setup, use the
[copy-and-paste diagnostics and system settings](docs/standalone-hardening/README.md#collect-mpi-and-fabric-diagnostics).
It locates the saved trial installations and prints the exact local report path
to share. Keep using this README and its linked workflow for current procedures.

For a stalled FFTW MPI check or a UD QP permission error, follow
[the bounded MPI startup diagnostic](docs/standalone-hardening/README.md#fftw-mpi-check-hangs-or-reports-a-ud-qp-permission-error)
before retrying the package suite. It compares startup components without
changing completed builds or saved runtime settings.
After startup passes, use [the package continuation steps](docs/standalone-hardening/README.md#continue-package-builds-after-startup-passes)
to save the component selection, check installation state and finish both build arms.

If UCX is already installed without RDMA support, follow
[the MPI graph recovery](docs/standalone-hardening/README.md#recover-a-completed-tcp-only-mpi-build-for-rdma).
It preserves serial progress, archives the old MPI graph, saves the RDMA
selection and rebuilds through the existing full/reference driver workflow.

Maintainers can exercise the UCX configure/binding regression using the pinned
release archive and a locally available Linux Go/GCC Docker image:

```bash
python3 scripts/check_ucx_go_bindings.py /path/to/ucx-1.16.0.tar.gz
```

The check verifies the archive checksum, runs the actual recipe's configure
command and optional-binding target with Go installed, and uses a disposable
container with networking disabled. It does not run the target-system package
builds or performance campaign.

The parallel HDF5 configuration regression uses the pinned release archive and
a local Linux image with CMake 3.26+, GCC, Python 3 and system Open MPI under
`/usr` (no MFU, libcircle or DTCMP required):

```bash
python3 scripts/check_hdf5_mpi_configure.py /path/to/hdf5-2.1.0.tar.gz --image YOUR_LINUX_MPI_CMAKE_IMAGE
```

It configures the actual recipe for both arms with system compilers and neutral
flags in a disposable container with networking disabled, and checks that MPI,
parallel test targets and regular tools remain enabled. Target GCC hardening,
package builds/tests and fabric qualification remain separate checks.
