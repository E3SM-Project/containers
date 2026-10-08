# E3SM images

Development and testing environments for E3SM: a spack-built software stack on UBI9,
runnable anywhere with podman, docker or Apptainer (see
[Apptainer / HPC](#apptainer--singularity-on-hpc-systems)). Software only -- no input data is baked in; mount
what you need.

## GitHub container registry (GHCR) authentication

Public images can be pulled anonymously. If you need authenticated access to GHCR:

1. **Create a personal access token (PAT):**
   - Go to your GitHub account **Settings > Developer settings > Personal access tokens**.
   - Generate a classic token with the **`read:packages`** scope enabled (plus `write:packages` if you plan to push images).

2. **Log in via podman:**
   ```bash
   podman login ghcr.io
   ```

## Quick start

```bash
podman run --rm -it --userns=keep-id:uid=1000,gid=1000 \
  -v /path/to/host/inputdata:/projects/e3sm/data/inputdata:z \
  -v /path/to/host/baselines:/projects/e3sm/data/baselines:z \
  ghcr.io/e3sm-project/e3sm-image:gnu13-openmpi4
```

The default command is `bash --login`. `--userns=keep-id:uid=1000,gid=1000` makes the
mounts writable under rootless podman; drop it with docker (see
[The default user](#the-default-user)).

### Running a command in the image

The whole environment (lmod modules, `SPACK_ARCH`, the compiler, the python venv) is set
up by `/etc/profile.d`, which only a **login** shell reads. The images handle that for you
wherever they can:

- **`docker run` / `podman run` with a command** goes through the image's entrypoint,
  `e3sm-env`, which starts a login shell and `exec`s the command in it. So
  `podman run --rm IMAGE cmake --version` or `podman run --rm IMAGE python3 script.py`
  (the venv's python) just work; arguments are passed through unchanged, and signals and
  the exit status are the command's own. `--entrypoint ''` gets you the bare image.
- **`docker exec` / `podman exec` never use the entrypoint**, so a command there has the
  image's `ENV` but none of the login environment. Use `podman exec -it CONTAINER bash -l`
  for a shell, or `podman exec CONTAINER e3sm-env <command>`.
- The same goes for anything else that starts a process in an existing container without
  a login shell -- devcontainer lifecycle hooks (`sh -c`), `apptainer exec`: wrap the
  command in `e3sm-env`.

An interactive shell should still be a login shell (`bash -l`, which the default command
is): it also gets the history key bindings and, in the `-dev` images, the prompt and
completion, which profile.d sets up but cannot export.

## Available images

Every image is published under a single, arch-independent tag. Each tag is a multi-arch
manifest list holding a natively-built image (no emulation) for each arch listed below, so
`podman pull` resolves to whatever arch you are on and nothing here needs an arch in its
name. The Intel images are `x86_64` only, and every `x86_64` image needs an **x86-64-v3**
CPU (AVX2: Intel Haswell / AMD Excavator or newer), the target the binary cache is built for:

Tags name the compiler and MPI by major version (`gnu13-openmpi4`), plus the accelerator
when there is one (`-cuda`); no accelerator means a host-only stack. The exact versions are
in `/etc/e3sm/image.env` inside the image.

| Tag                  | Arches          | Compiler      | MPI          | Notes |
|----------------------|-----------------|---------------|--------------|-------|
| `gnu13-openmpi4`     | x86_64, aarch64 | GCC 13        | Open MPI 4   | CPU-only stack; the aarch64 image runs well on Apple Silicon |
| `gnu13-mpich4-cuda`  | x86_64, aarch64 | GCC 13        | MPICH 4      | CUDA stack: 12.4 on x86_64, 13.0 on aarch64, which targets NVIDIA "superchip" systems such as Grace Hopper/Blackwell |
| `intel2024-openmpi4` | x86_64          | oneAPI 2024.1 | Open MPI 4   | CPU-only stack (Intel oneAPI is x86_64-only) |
| `<tag>-dev`          | as above        | as above      | as above     | Any of the above plus developer tooling; see below |

Every env image also carries `less`, `nano`, `screen` and `zip`, so a shell in the image
the tests run in is usable for debugging.

The x86_64 images target `x86_64_v3` (AVX2: Intel Haswell / AMD Excavator and newer), which is
what the binary cache below is built for; the aarch64 images are fully generic.

To pull a specific arch on a host of the other arch (under emulation), ask for the
platform rather than a different tag:

```bash
podman pull --platform linux/arm64 ghcr.io/e3sm-project/e3sm-image:gnu13-openmpi4
```

## The `-dev` images

`<tag>-dev` is the matching env plus the things you want when you actually work inside the
container rather than just run tests in it:

- **Coding agents:** `claude`, `codex`, `copilot`, `opencode`
- **Python tooling:** `uv` (and `uvx`)
- **Build loop:** `ccache`, `ninja`, `gdb`, `strace`
- **Shell/CLI:** `gh`, vim, `ripgrep`, `fzf`, `tig`, `bat`, `ncdu`,
  `git-lfs`, bash completion, a git-aware prompt, sensible history settings
- **Node** (upstream build, since the UBI9 package is EOL node 16), so `npm i -g` works

Each agent and `uv` is installed from its own upstream installer into `$HOME`, as the
`e3sm` user, so they self-update inside a running container with no root and no rebuild:

```bash
uv self update
claude update
opencode upgrade
codex --upgrade
copilot --version   # self-updates on run
```

They start you in `/projects/e3sm/work`, also linked at `~/work`, which is on the same
tree as the data mounts, so a clone there is easy to bind-mount out.

`tmux`, `htop` and `tree` are in neither the UBI9 package subset nor EPEL9; `screen` is
the multiplexer that is available.

### Using it as a devcontainer

`devcontainer.json.example` in `ghci/dev/` is a working starting point to copy into a
repo's `.devcontainer/`. The one thing that will bite you if you write your own: the entire
environment (modules, `SPACK_ARCH`, the venv) lives in `/etc/profile.d`, which only a
**login** shell sources. So set `"userEnvProbe": "loginInteractiveShell"`, give the
integrated terminal a `bash -l` profile, and wrap lifecycle hooks -- which run under
`sh -c` -- in `e3sm-env`:

```jsonc
"postCreateCommand": "e3sm-fix-ownership && e3sm-env git submodule update --init --recursive"
```

(`e3sm-fix-ownership` is for Linux hosts whose uid is not 1000; see
[The default user](#the-default-user).)

`e3sm-env <cmd>` runs a command with the full login environment from a context that has
none. It is also the images' entrypoint, but Dev Containers starts the container with its
own command and runs the hooks through `docker exec`, so neither goes through it. Without
it, `postCreateCommand` cannot find a compiler.

**Credentials.** `git push` over SSH needs no setup: VS Code forwards your ssh-agent, and
the `-dev` images drop the base image's `git@github.com:` -> HTTPS rewrite (which exists so
CI can fetch submodules anonymously, but would otherwise override an SSH remote and prompt
for a password). For `gh` and the agent CLIs, pick one of the two mount blocks in the
example: empty named volumes and log in once inside (nothing from the host is exposed), or
bind your host config dirs for a working-on-first-launch setup -- at the cost of every
process in the container, agents included, being able to read those credentials. Note that
`gh`, `codex`, `copilot` and `opencode` keep their credentials in files, so bind-mounting
those works. Claude Code on macOS keeps its token in the **Keychain**, so it cannot be
mounted in -- log in once inside and the `~/.claude` volume keeps it across rebuilds.

**Trust.** A bind-mounted checkout is owned by your host uid, which git calls "dubious
ownership" when it is not the container user's. The `-dev` images mark everything under
`/projects/e3sm/work` (submodules included) as safe for git, and nothing else; for a
checkout elsewhere, run `git config --global --add safe.directory <path>` once. The example
leaves VS Code's Workspace Trust on, so VS Code asks once whether to trust the folder (and
may ask again after a rebuild); its comments show how to turn the prompt off and what that
costs.

## The default user

The images run as **`e3sm` (uid/gid 1000)**, not root, with passwordless `sudo`:

- MPI implementations refuse to run as root, so this removes the usual `mpirun`
  workarounds.
- With docker (and rootful podman), files written into bind mounts come back owned by
  uid 1000, which is the first user on most Linux hosts, so ownership usually lines up
  with no extra flags.
- **Rootless podman is different**: by default your host user maps to container *root*,
  and container uid 1000 maps to a subordinate uid, so `e3sm` cannot write to your
  bind-mounted checkout. Map your host user onto `e3sm` explicitly (podman 4.3+):
  `podman run --userns=keep-id:uid=1000,gid=1000 ...`. Plain `--userns=keep-id` runs
  as your host uid instead, which cannot write to the image's own `/projects/e3sm`
  paths unless that uid happens to be 1000.
- `--user root` gets you a root shell if you need one.
- **Dev Containers on Linux** (`"updateRemoteUserUID": true`, as in the example) changes
  `e3sm`'s uid/gid to yours when your host uid is not 1000, but only re-owns the home
  directory. The python venv and `/projects/e3sm` stay owned by uid 1000, so `pip install`
  and creating anything next to the checkout fail. The `-dev` images carry
  `e3sm-fix-ownership`, which hands those to the current user; the example runs it from
  `postCreateCommand`, and so should your own `devcontainer.json`. With uid 1000 (and on
  macOS and Windows, where nothing is remapped) it returns at once; after a remap it copies
  the venv into the container's writable layer once (1-6 GB depending on the image), which
  can take a minute. It leaves what is inside `/projects/e3sm/data` and
  `/projects/e3sm/work` alone: those are your bind mounts.
- At the labs your uid is usually not 1000, and shared inputdata/baselines are reachable
  through a group instead. Hand that group to the container: with docker,
  `--group-add $(stat -c %g /path/to/baselines)`; with rootless podman, whose user
  namespace does not map host gids, `--group-add keep-groups`.

Builds run as root; the env and `-dev` images switch to `e3sm` at the end.

## Apptainer / Singularity on HPC systems

HPC systems rarely have docker or podman; they have Apptainer (formerly Singularity). The
images work there, but several things behave differently from `docker run`. Everything
marked *tested* is run by `ghci/tests/apptainer.sh`, which CI runs against the published
`gnu13-openmpi4` image on x86_64 with Apptainer 1.4 (user-namespace mode); the rest is
documented from the image's contents and has not been run on real HPC hardware.

```bash
# the SIF is a single read-only file, so build it once, somewhere with room
export APPTAINER_CACHEDIR=$SCRATCH/apptainer-cache APPTAINER_TMPDIR=$SCRATCH/tmp
apptainer pull e3sm-image-gnu13-openmpi4.sif docker://ghcr.io/e3sm-project/e3sm-image:gnu13-openmpi4

apptainer run --cleanenv \
  --bind /path/to/inputdata:/projects/e3sm/data/inputdata \
  e3sm-image-gnu13-openmpi4.sif
```

For a private GHCR package, set `APPTAINER_DOCKER_USERNAME` and `APPTAINER_DOCKER_PASSWORD`
(a PAT with `read:packages`) before pulling. Tags are multi-arch, so the pull gets the
native image.

What differs from docker/podman:

- **You are not `e3sm`.** Apptainer runs as your own host user and uid, with your own
  `$HOME`. The `e3sm` user, its uid 1000 and its home are not used, and `sudo` does not
  work (nor is it needed: MPI is happy as a non-root user, and files written to bind mounts
  are owned by you). *Tested.* `E3SM_USER` is still set to `e3sm`; ignore it.
- **Get a login shell.** The environment (modules, `SPACK_ARCH`, the compiler, the venv)
  lives in `/etc/profile.d`, which only a login shell reads, and `apptainer exec` does not
  start one. *Tested:*
  - `apptainer run img.sif` runs the image's default command, `bash --login`;
  - `apptainer run img.sif <command>` runs the command through the image's entrypoint,
    `e3sm-env`;
  - `apptainer exec img.sif bash -l -c '<command>'`;
  - `apptainer exec img.sif e3sm-env <command>`.

  `apptainer exec` does not use the entrypoint, so a plain
  `apptainer exec img.sif cmake --version` finds none of the modules.
- **Use `--cleanenv` (`-e`).** By default your host environment is passed into the
  container, so host `PATH`, `LD_LIBRARY_PATH`, `PYTHONPATH`, certificate-bundle variables
  and the like can shadow or break what the image provides. `--cleanenv` keeps the image's
  own `ENV` and drops the rest; pass what you need on purpose with `--env NAME=value` (for
  example `http_proxy` for `pip` on a node behind a proxy). *Tested.*
- **The image is read-only.** The venv (`/projects/e3sm/software/eamxx-venv`) and
  `/projects/e3sm` cannot be written to, so `pip install` fails. Three ways round it, all
  *tested*:
  - `--writable-tmpfs`: writes go to memory and vanish when the container exits; right
    for trying a package or for a quick test;
  - `--overlay`: `apptainer overlay create --size 1024 overlay.img`, then
    `--overlay overlay.img`; writes persist in that file, which is one file on a
    parallel filesystem rather than many small ones;
  - install elsewhere and point at it, e.g. `pip install --target $SCRATCH/pylibs ...`
    and `PYTHONPATH=$SCRATCH/pylibs`. (`pip install --user` does not work in a venv.)
- **Mounts.** Your `$HOME`, `/tmp` and the current directory are mounted automatically.
  Bind everything else with `--bind host:container`, as in the quick start above;
  `/projects/e3sm/data/inputdata` does not need to exist in the image. *Tested.* The
  SELinux `:z` suffix is a podman/docker option; do not use it. Access to
  group-shared data depends on how the site configures Apptainer (setuid or user
  namespaces); check that you can read it from inside before relying on it.

### MPI

- **One node: works.** `mpirun -n N` inside the container, as the smoke test does with two
  ranks and C, `mpi` and `mpi_f08` programs. *Tested.* Run it under your scheduler's
  allocation, e.g. `srun -N1 -n1 apptainer exec ... mpirun -n 16 ./a.out`; `mpirun` inside
  the container does not know about Slurm and uses every core it can see unless told
  otherwise.
- **Several nodes: not qualified, and not tuned.** The default image's Open MPI 4.1.4 is
  built from spack with only the `self`, `vader` (shared-memory) and `tcp` transports: no
  `ucx`, `libfabric`/OFI, verbs or PSM, and no Slurm launcher. So inside the container,
  traffic between nodes can only go over TCP, and `mpirun` cannot start ranks on other
  nodes through Slurm. The usual options are:
  - *Hybrid*: launch with the host's `srun`/`mpirun` (`srun ... apptainer exec img.sif
    ./a.out`) so the host MPI starts the container processes. This needs a host MPI whose
    PMI/PMIx and ABI match the container's, and is something a site has to arrange.
  - *Bind-mount the site MPI and its fabric libraries* into the container and build E3SM
    against them rather than the image's MPI.

  Which fits depends on the site's MPI and interconnect (Slingshot, InfiniBand, ...).
  Treat the image as a development and testing environment on such systems, not as a
  production MPI runtime, unless you have set one of these up and validated it.

### GPUs

The CUDA images carry the CUDA toolkit and CUDA-enabled Torch/CuPy but, as with docker,
no driver. Apptainer's `--nv` injects the host's NVIDIA driver libraries into the
container. That is the expected way to run on a GPU node but has **not** been qualified:
CI has no GPU, and tests only that the CUDA images import and that `nvcc` compiles a
kernel. The host driver must be new enough for the image's CUDA (12.4 on x86_64, 13.0 on
aarch64).

## Important storage & permission guidelines

- **Input data** (`inputdata`): mount it at `/projects/e3sm/data/inputdata`. The `e3sm`
  user owns `/projects/e3sm`, so downloads into it work without root.
- **Baselines** (`baselines`): optional; omit the mount if you are not comparing against
  baselines.
- **SELinux** (`:z`): on an SELinux-enforced host (RHEL, Fedora), append `:z` to volume
  mounts so podman relabels them.

## Running E3SM (CIME)

Every image carries its own CIME machine, **`e3sm-container`**, in `~/.cime`, and the login
environment exports `CIME_MACHINE=e3sm-container`. So in any runtime, with no `--machine`
and no `--hostname` trick:

```bash
cd /projects/e3sm/work/E3SM/cime/scripts
./create_test SMS_P8_Ln5.ne4pg2_oQU480.F2010 --wait
./create_newcase --case ~/e3sm_scratch/mycase --compset F2010 --res ne4pg2_oQU480
```

- **Which compiler and MPI**: the image's own; a CUDA image defaults to `gnugpu` and can
  also build for the CPU with `--compiler gnu`. `query_config --machines e3sm-container`
  lists them. (`query_config --machines current` guesses from the hostname instead, and a
  docker hostname matches E3SM's `ghci-snl`.)
- **Where things go**: inputdata in `/projects/e3sm/data/inputdata` (mount it; CIME downloads
  what is missing), baselines in `/projects/e3sm/data/baselines/<compiler>`, cases and
  builds in `~/e3sm_scratch` (`create_test --output-root` changes it).
- **Cores**: one node of whatever cores the container sees. Tests asking for more ranks
  than that still run, oversubscribed. Builds use 8 make jobs (`./xmlchange GMAKE_J=N`).
- **GPU arch**: the CUDA images build for Hopper (`HOPPER90`) unless `E3SM_KOKKOS_CUDA_ARCH`
  names another Kokkos arch, e.g. `AMPERE80`.
- **EAMxx standalone**: `components/eamxx/scripts/test-all-eamxx -m e3sm-container` uses the
  same machine (`~/.cime/scream_mach_specs.py`).
- **Another user or HOME**: CIME reads machines only from `$HOME/.cime`, and the files are in
  `e3sm`'s home. Anyone else (`--user <uid>`, Apptainer, which brings your host `$HOME`)
  gets CIME's usual behavior -- no `CIME_MACHINE` -- until they copy the pristine set in:
  `mkdir -p ~/.cime && cp /etc/e3sm/cime/* ~/.cime/`, then log in again.
- **Your own settings win**: an explicit machine (in a test name, `--machine`, or your own
  `CIME_MACHINE`) is used as before, so E3SM's `ghci-snl` entries still work in these images.
  `~/.cime` is yours to edit.

CI checks this with `ghci/tests/e3sm-case.sh` (`.github/workflows/e3sm-case.yaml`):
nightly against the published images and E3SM master, and on PRs that change the machine.
It builds and runs `SMS_Vmoab_P8_Ln5.ne4pg2_oQU480.WCYCL2010NS` and
`SMS_P8_Ln5.ne4_ne4.F2000-SCREAMv1-AQP1` (`eamxx-L72` testmod), then the EAMxx standalone
`-t sp` tests; the CUDA images only build the cases (CI has no GPU). To run it locally
against your own checkout, see the script's header.

## Python environment & custom packages

The container comes pre-configured with a virtual environment named `eamxx-venv`, activated
at login. Extra packages can be installed on the fly:

```bash
pip install <package-name>
```

They persist for the life of the container, which is disposable by design.

`mpi4py` is built from source against the image's MPI, so it uses the same `mpirun` and
library as the compiled code. `netCDF4` is the PyPI wheel, which carries its own serial
copies of netCDF-C and HDF5 (`netCDF4.__netcdf4libversion__`,
`netCDF4.__hdf5libversion__`) rather than using spack's; that is fine for reading and
writing files -- the smoke test checks it reads what the spack stack writes -- but it has
no parallel I/O. For that, build it against spack's libraries (not tested by CI):
`HDF5_DIR=$HDF5_ROOT NETCDF4_DIR=$NETCDF_C_ROOT pip install --no-binary netCDF4 netCDF4`.

## Manually rebuilding the stack

To test a different compiler or library version, rebuild locally. Each image builds for the
arch you are on; there is no arch build arg to set. Every build arg has the `gnu13-openmpi4`
value as its default, so this alone builds that image:

```bash
podman build --tag e3sm-image:gnu13-openmpi4 ghci/env/
```

and, for example, gcc 15 with openmpi 5:

```bash
podman build \
  --build-arg GCC_TOOLSET=15 \
  --build-arg MPI_SPEC=openmpi@5.0.10 \
  --tag e3sm-env:gnu15-cpu-env \
  ghci/env/
```

The args (see the top of each section in `ghci/env/Dockerfile`, and the `env` matrix in
`.github/workflows/ghci.yaml` for the published variants):

| Arg                | Default                      | Notes |
|--------------------|------------------------------|-------|
| `COMPILER`         | `gcc`                        | or `intel-oneapi-compilers` |
| `GCC_TOOLSET`      | `13`                         | gcc major; UBI9 has 13 (13.3.1), 14 (14.2.1) and 15 (15.2.1), and the toolset decides the exact version |
| `INTEL_VERSION`    | `2024.1.0`                   | oneAPI release, when `COMPILER=intel-oneapi-compilers` |
| `MPI_SPEC`         | `openmpi@4.1.4`              | any spack spec, e.g. `openmpi@5.0.10`, `mpich@4.1.1` |
| `LAPACK_SPEC`      | `openblas`                   | e.g. `netlib-lapack`, `intel-oneapi-mkl` |
| `WITH_DEBUG_TOOLS` | `yes`                        | gdb and valgrind, from RHEL |
| `WITH_CUDA`        | `no`                         | |
| `WITH_MOAB`        | `yes`                        | MOAB 5.6.0 (with TempestRemap) from spack; its module exports `MOAB_ROOT` |

## How the images are put together

`<tag>` -> `<tag>-dev`. That is two Dockerfiles, not one per variant:
`ghci/env/Dockerfile` builds every env from build args, and the variant list is the `env`
matrix in `.github/workflows/ghci.yaml` (defined once there; the other jobs reuse it). `ghci/dev/Dockerfile` is likewise one recipe for
all the `-dev` images, built `FROM` the env tag.

The env Dockerfile is ordered from most to least shared: system packages and spack first
(no build args involved, so every variant on a runner reuses those layers), then the
compiler, then the spack stack in chunks, then the python venv.

**Compilers.** gcc is not built: it is RHEL's `gcc-toolset-N`, enabled for login shells
from `/etc/profile.d/gcc-toolset.sh`. Intel oneAPI is installed by spack (a download, not a
build) and loaded as an lmod module.

**The binary caches.** Spack is configured (`ghci/env/spack-configuration/`) to reuse
prebuilt binaries from two caches. The first is our own, on GHCR (see below). The second is
the [E4S](https://oaciss.uoregon.edu/e4s/inventory.html) build cache,
`https://cache.e4s.io/26.06`. Its rocky9 stack matches UBI9 (same glibc, 2.34) and
is built with `gcc-toolset-13`, so with gcc 13.3.1 most of the tree -- cmake, python,
boost, yaml-cpp, and nearly every dependency -- is downloaded in seconds instead of built.
Whatever the cache does not have (a version, variant or compiler it was not built with) is
built from source exactly as before; the cache never changes *what* gets installed, only
how long it takes. In the default gnu13-openmpi4, what still builds is openmpi 4 (E4S only has
openmpi 5) and the MPI-dependent I/O libraries and MOAB (E4S builds those against
its own external mpich). gdb and valgrind come from RHEL.

Our own cache, `oci://ghcr.io/e3sm-project/e3sm-spack-buildcache`, holds what E4S does not
have: openmpi 4, the MPI-dependent I/O libraries and MOAB, and what is built with the oneAPI
compilers. Packages whose recipe forbids binary redistribution, such as the oneAPI compilers
and MKL themselves, are not pushed (the cache is public); spack downloads those rather than
building them, so this costs little.
The `buildcache` job in `.github/workflows/ghci.yaml` pushes every package installed in an
env image to it, per arch, once that image has passed its smoke tests, then the
`buildcache-index` job refreshes the index (spack only installs what the index lists).
Packages already in the cache are skipped, so a rebuild uploads only what is new. Only pushes
to `main`, `ghci-*` tags and manual runs (which need write access, and can name any branch)
publish; PRs and merge-queue runs only read the cache, so an unreviewed change never puts a
binary there. Since the concretizer prefers what is in the cache, what gets pushed also shapes
later builds' solutions. The two jobs are not part of `required-check`: a failed push is a red
job, not a blocked merge. Binaries are unsigned
(OCI mirrors are not signed by spack) and read anonymously, so the `e3sm-spack-buildcache`
package must be public: after the first publish, set its visibility in the package settings on
GitHub. To use it outside these images, `spack mirror add --unsigned e3sm
oci://ghcr.io/e3sm-project/e3sm-spack-buildcache` on rocky9/RHEL9 with spack 1.x.

The package recipes are pinned to the same release the cache was built from
(`repos.yaml`), so the two move together: to bump, change the spack version in the
Dockerfile, the `tag` in `repos.yaml` and the E4S release in `mirrors.yaml` at once.

Nothing here is parameterized by arch. The image writes `SPACK_ARCH=linux-rhel9-<target>`
into `/etc/profile.d/spack-arch.sh` at build time and pins spack to that target, so each
arch picks up the right one on its own (profile.d rather than `ENV`, since `ENV` cannot be
computed at build time -- hence the `bash --login` CMD, and every `RUN` in the Dockerfile
starting with `. /etc/profile`: a `SHELL` instruction would be simpler, but it only works
with Docker-format builds, and podman/buildah build OCI images by default). CI builds
each arch natively, pushes by digest, and merges the digests into one manifest list per
tag; see `.github/workflows/build-multiarch.yaml`.

## Relationship to `ghci-snl`

These recipes started life as `ghci-snl/`, which has been removed from this repository. There
is nothing SNL-specific in them, and nothing tied to GitHub Actions either -- they run
anywhere.

## Size reports and runtime checks

For same-repository PRs, CI tests every published env/platform combination as the non-root
user (and `gnu13-openmpi4` on x86_64 again under Apptainer, see above): login environment,
commands run without a login shell (through `e3sm-env`), writable venv, Python dependency
consistency, NetCDF round-trip, Torch flavor, two-rank MPI programs in C, Fortran and
Python (`mpi4py`, checked to be linked against the image's MPI), Python `netCDF4` reading
files the spack stack wrote, and parallel netCDF/PnetCDF I/O. The `-dev` images get the
same checks plus their own (`ghci/tests/smoke-dev.sh`): the dev tools and agents on PATH,
and the ownership of the dirs a dev container mounts onto. Each smoke job uploads an
`image-size-<tag>-<arch>` artifact with exact bytes, image ID, and layer commands, and the
run's summary page has one table of every image's compressed and expanded size.

`ghci/tests/dev-container.sh` holds the `-dev` image checks that need root to set up (git
in a checkout owned by another uid, a Dev Containers uid remap). CI does not smoke-test
the `-dev` images yet, so it is not run there; run it by hand as its header shows.

The ARM CUDA image currently has one verified upstream packaging defect:
`nvidia-cusparselt-cu13==0.8.1` has an `aarch64` wheel filename but an internal
`manylinux2014_sbsa` tag. The dependency check warns and continues only for that exact
version, tag, Linux ARM64 CUDA environment, and lone pip diagnostic. Any other error
still fails, and all runtime tests must pass. This does not establish GPU execution;
that requires an NVIDIA host. Package files are not modified by this exception.

To inspect images already present in a local Docker engine, without building or pulling:

```bash
python3 scripts/image-size.py BASELINE_IMAGE CANDIDATE_IMAGE
python3 scripts/image-size.py CANDIDATE_IMAGE --json > image-size.json
```

Compare the same platform and variant. These are uncompressed layer totals, not registry
download sizes or unique disk usage across shared images.
