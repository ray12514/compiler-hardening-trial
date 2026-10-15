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

Maintainers can exercise the UCX configure/binding regression using the pinned
release archive and a locally available Linux Go/GCC Docker image:

```bash
python3 scripts/check_ucx_go_bindings.py /path/to/ucx-1.16.0.tar.gz
```

The check verifies the archive checksum, runs the actual recipe's configure
command and optional-binding target with Go installed, and uses a disposable
container with networking disabled. It does not run the target-system package
builds or performance campaign.
