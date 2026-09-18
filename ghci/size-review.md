# ghci size and maintenance review

Reviewed 2026-09-18 against `main` at `e37279a`, plus
`bartgol/ghci-dev` at `46e9d8a` and `bartgol/shrink-images-size` at `f422e27`.
There is no remote branch literally named `ghci`; the working branch starts from the
current `ghci/` recipes on main. The Git metadata is about 3 MB, so container layers
are the useful target for size reduction.

## Measured baseline

The locally cached `ghcr.io/e3sm-project/e3sm-ghci:gnu-cpu-env-pr-48` image is
`linux/arm64`, ID
`sha256:fb3af2226e5a1ede28bf9c73174c136bee87a3de00cf5d746d385f5ee7b78085`.
Docker reports **13,046,268,321 bytes** in uncompressed image layers.
This is an older PR image, not a fresh main build.

| Layer | Exact bytes | Finding |
| --- | ---: | --- |
| Final recursive `chown` of `/projects/e3sm` | 3,308,262,707 | Re-emits installed Python and MOAB files |
| Recursive `chmod` of the venv | 980,104,580 | Re-emits the Python environment |
| Combined permission layers | 4,288,367,287 | About 32.9% of this cached image |

These are measured existing layers, **not a measured before/after reduction**. The new
recipes eliminate those two late permission operations, but actual rebuilt sizes depend
on resolved dependencies, platform, and other layer changes. Compare the CI size artifacts
for equivalent variants before claiming a percentage reduction.

## Changes in this branch

1. Create the venv and install Python packages as `e3sm`, eliminating world-writable
   packages and both late recursive permission layers. Set MOAB ownership in its install
   layer. Return to root only for system and Spack operations.
2. Clean Spack caches in every install layer; disable pip download/wheel caching in
   image builds. Keep Spack bootstrap tools and installed dependencies intact during
   these cleanup steps. Keep the existing final `spack gc` behavior.
3. Keep PyPI as the primary source and add the selected Torch CPU/CUDA index with
   `--extra-index-url`, as required by the existing install contract. Disable pip's
   download and wheel cache in the image layers.
4. Retain the Spack checkout: removing files inherited from the base image hides them
   without reclaiming their layer bytes, and prevents useful inspection of the stack.
5. Fail fast on Spack failures and enable pipeline failure propagation for developer
   tool installers. A failed `curl | sh` must not look like a successful installation.
6. Add fast Dockerfile syntax and Actions lint before expensive builds, runtime smoke
   checks after publication, and size reports per env/platform. Replace word-split
   manifest arguments with shell arrays. Correct outdated contributor/authentication docs.

The existing size-reduction branch already proposes same-layer cleanup. Its final
Dockerfile omits separators after `spack clean -a` in the CUDA, MOAB, and debugging
conditionals: two fail Bash parsing; the CUDA branch swallows `else` into the command.
The new syntax checker catches the two parser failures. Static lint cannot replace builds.
The static-MOAB change is now on main. Downstream E3SM consumer testing remains necessary
before making further MOAB reductions.

## Remaining opportunities

| Priority | Follow-up | Evidence / validation needed |
| --- | --- | --- |
| High | Audit MOAB's retained source/build trees and static libraries | Its old install layer alone is about 2.33 GB. Inspect the bootstrap outputs and validate downstream E3SM linking before deleting files. |
| High | Pin moving dependencies and record provenance | UBI `latest`, Python packages, the E3SM clone, MOAB branch, and agent installers can change between builds. Record image digests and resolved versions before a broad pinning update. |
| Medium | Separate optional Torch/debug/agent tooling from lean CI variants | Requires confirmation of what E3SM/EAMxx tests actually consume; existing tag capabilities are preserved here. |
| Medium | Revisit build-only Spack dependencies using builder stages | The late `spack gc` cannot shrink earlier layers. Removing dependencies after each install can force repeated builds; measure this tradeoff first. |
| Medium | Audit registry retention separately from image size | Cleanup uses package creation time, which is not last-use time when a digest is retagged. Freshly reused caches may age out. Registry writes and deletion policy are unchanged here. |
| Medium | Improve fork-PR stage chaining | Fork builds still use published main parents; they do not validate a changed base/compiler chain together. The new runtime checks deliberately skip forks instead of testing main's images. |

## Validation

- All four current Dockerfiles pass shell syntax checks (59 shell RUN instructions).
- All Actions workflows pass actionlint 1.7.7, including its ShellCheck integration.
- The smoke script passes Bash parsing; the size reporter was exercised on the cached image.
- The unchanged base image rebuilt successfully from local Docker cache before the
  decision to move builds to CI. The attempted compiler baseline build was cancelled.
- At initial publication, full updated builds and runtime smoke results were pending
  GitHub Actions; see the follow-up below. No local full-stack size reduction, CUDA
  execution, or downstream E3SM test result is claimed.

### ARM CUDA dependency-check follow-up

The initial CI build completed all image variants; four of the five env/platform smoke
tests passed. The ARM CUDA smoke job stopped at `pip check`, before importing Torch,
with `nvidia-cusparselt-cu13 0.8.1 is not supported on this platform`.
Inspection of the NVIDIA wheel linked by the official cu130 index confirmed a filename
ending in `manylinux2014_aarch64.whl` but internal `WHEEL` metadata declaring
`Tag: py3-none-manylinux2014_sbsa`.

The smoke test now permits only that single diagnostic with exit status 1, on Linux
ARM64 with `EXPECT_CUDA=yes`, after checking the installed package version and exact
internal tag. It preserves pip's output, emits a warning, leaves package files untouched,
and continues the runtime tests. Additional diagnostics, different versions/tags/platforms,
missing metadata, and unexpected exit statuses still fail. Regression tests cover these
guards. Updated online smoke results remain pending; no GPU execution is claimed.

Evidence: [failed ARM smoke job](https://github.com/E3SM-Project/containers/actions/runs/35299045096/job/105660401893)
and [official cu130 wheel index](https://download.pytorch.org/whl/cu130/nvidia-cusparselt-cu13/).

Reference behavior: [Docker layer storage](https://docs.docker.com/engine/storage/drivers/),
[pip caching](https://pip.pypa.io/en/stable/topics/caching/),
[Spack 0.23.1 cleanup implementation](https://github.com/spack/spack/blob/v0.23.1/lib/spack/spack/cmd/clean.py),
and [PyTorch installation](https://pytorch.org/get-started/locally/).
