# E3SM containers

Container recipes for the E3SM project. Each top-level directory is one family of images,
built and published to GHCR by the matching workflow in `.github/workflows/`.

These images are software environments for building and running E3SM: compilers, MPI, the
I/O libraries and Python stack E3SM needs. They do not contain E3SM itself (its source or
executables) or any input data; check out E3SM and mount your data into the container.

## Which image do I want?

All are `ghcr.io/e3sm-project/e3sm-image:<tag>`, one multi-arch tag per image:

| Tag                  | Arches          | Toolchain                     | Use it for |
|----------------------|-----------------|-------------------------------|------------|
| `gnu13-openmpi4`     | x86_64, aarch64 | GCC 13, Open MPI 4            | CPU builds and tests; the default choice, including on Apple Silicon |
| `gnu13-mpich4-cuda`  | x86_64, aarch64 | GCC 13, MPICH 4, CUDA         | NVIDIA GPU builds (CUDA 12.4 on x86_64, 13.0 on aarch64) |
| `intel2024-openmpi4` | x86_64          | oneAPI 2024.1, Open MPI 4, MKL | CPU builds with the Intel compilers |
| `<tag>-dev`          | as above        | as above                      | Working inside the container: debuggers, ninja, ccache, coding agents |

```bash
podman run --rm -it ghcr.io/e3sm-project/e3sm-image:gnu13-openmpi4
```

- **CPU:** the x86_64 images need an **x86-64-v3** CPU (AVX2: Intel Haswell / AMD Excavator or
  newer). The aarch64 images are generic.
- **GPU:** the CUDA images carry the CUDA toolkit, not the driver; that comes from the host.
  CUDA 12.4 needs driver 550 or newer (525 with CUDA minor-version compatibility), CUDA 13.0
  needs 580 or newer.

How to run them (podman, docker, Apptainer, Dev Containers), what is in them, and how they
are built: [`ghci/README.md`](ghci/README.md).

## Images

| Directory                                        | Image                                                  | What it is |
|--------------------------------------------------|--------------------------------------------------------|------------|
| [`ghci/`](ghci/)                                 | `ghcr.io/e3sm-project/e3sm-image`                      | Spack/UBI9 development and testing environments (`gnu13-openmpi4`, `gnu13-mpich4-cuda`, `intel2024-openmpi4`, and a `-dev` variant of each). **Start here.** |

## Conventions

- **Software and data are separate.** Images carry a software stack; data gets mounted in.
  This repo builds no data images: `inputdata` and `e3sm-diags-test-data` were removed, and
  their existing packages on GHCR are frozen rather than deleted.
- **One tag per image, no arch in the name.** Images supporting more than one architecture
  are published as multi-arch manifest lists, so `podman pull <tag>` gets you the native
  image for whatever machine you are on, and each arch is built natively rather than under
  emulation. To force one, use `--platform linux/amd64` / `--platform linux/arm64`, not a
  different tag. `.github/workflows/build-multiarch.yaml` implements this once for
  everyone.
- **Tag suffixes.** `<tag>` is what `main` publishes; `<tag>-<version>` comes from a
  release tag such as `ghci-1.2.3`. Both only ever point at images that passed CI's smoke
  tests: they are retagged from a tested build, never built directly. `<tag>-pr-<N>` is a
  pull request build; `-mg-<sha>` (merge queue) and `-rc-<run>` (release candidate) tags are
  CI's staging tags and are cleaned up after two days.
- **Non-root by default.** Runtime images run as `e3sm` (uid 1000) with passwordless
  `sudo`, because MPI refuses to run as root and bind-mounted files should not come back
  owned by root.
- **Runs under Apptainer too.** HPC users pull the same images with
  `apptainer pull docker://...`; the differences (host user, read-only image, login shell,
  MPI across nodes, GPUs) and what CI checks are in [`ghci/README.md`](ghci/README.md).
- **Prebuilt where possible.** Spack stacks reuse binaries from the E4S build cache and
  build only what it does not have; see [`ghci/README.md`](ghci/README.md).
- **Path-scoped builds.** The ghci workflow always reports its required check, but filters
  changes inside the workflow so unrelated edits skip the expensive builds.

Pull requests from forks cannot push to GHCR (`GITHUB_TOKEN` has no `packages: write`
there), so those runs build every stage as validation only, the `-dev` images FROM the env
image `main` published rather than the one the same run just built.

See [CONTRIBUTING.md](CONTRIBUTING.md) to add a new image.

CI runs shell/workflow lint before building, then checks the published env images and
uploads per-architecture size reports.

## Deprecated names

The images used to be published as `ghcr.io/e3sm-project/e3sm-ghci:<tag>`. Those tags are
still published, as aliases of exactly the same images (same digests), so nothing that pulls
them breaks; move to the new names, as the old ones will be removed once E3SM's own workflows
have switched.

| Old (`e3sm-ghci:`)  | New (`e3sm-image:`)       |
|---------------------|---------------------------|
| `gnu-cpu-env`       | `gnu13-openmpi4`          |
| `gnu-cuda-env`      | `gnu13-mpich4-cuda`       |
| `intel-cpu-env`     | `intel2024-openmpi4`      |
| `<old>-dev`         | `<new>-dev`               |
| `<old>-<version>`   | `<new>-<version>`         |
