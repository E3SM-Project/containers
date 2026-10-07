FROM registry.access.redhat.com/ubi9-minimal:latest

# One recipe for every env variant. The variants themselves (which args each one sets) are
# the matrix in .github/workflows/ghci.yaml; the defaults below are the gnu13-openmpi4 values.
# Nothing here is parameterized by arch: each arch is built natively and works out what it
# needs from `uname -m`.
#
# Layers are ordered from most to least shared: the system and spack layers do not depend on
# any build arg, so every variant built on the same runner reuses them.

# 1. Setup certificates
RUN microdnf update -y && \
    microdnf install -y ca-certificates && \
    update-ca-trust && \
    microdnf clean all && \
    rm -rf /var/cache/dnf

ENV SSL_CERT_DIR=/etc/pki/tls/certs \
    SSL_CERT_FILE=/etc/pki/tls/cert.pem

# 2. Setup EPEL repository
RUN rpm -ivh https://dl.fedoraproject.org/pub/epel/epel-release-latest-9.noarch.rpm && \
    sed -i 's/enabled=1/enabled=0/g' /etc/yum.repos.d/epel*.repo && \
    microdnf clean all && \
    rm -rf /var/cache/dnf

# 3. Build tools. No compiler here: gcc comes from gcc-toolset-N further down, which is also
# what keeps spack from ever picking up the system gcc.
RUN microdnf -y install \
        binutils \
        bzip2-devel \
        diffutils \
        file \
        glibc-devel \
        make \
        ncurses-devel \
        patch \
        pkgconfig \
    && microdnf clean all \
    && rm -rf /var/cache/dnf

# 4. Scripting runtimes (python & perl). CIME tests need the full perl.
RUN microdnf -y install \
        perl \
        perl-devel \
        python3 \
        python3-pip \
    && microdnf clean all \
    && rm -rf /var/cache/dnf

# 5. Utilities, archiving & environment tools
# NOTE: which, bc, findutils and rsync are not in ubi9-minimal, and build systems assume
# they exist -- CIME and configure scripts call `which nvcc`, `which mpicc` and friends.
# less, nano, screen and zip are the basics for debugging inside the image the tests run in.
RUN microdnf -y --enablerepo=epel install \
        bc \
        bind-utils \
        bzip2 \
        curl-minimal \
        findutils \
        git \
        gzip \
        hostname \
        iputils \
        jq \
        less \
        Lmod \
        nano \
        procps \
        rsync \
        screen \
        shadow-utils \
        sudo \
        tar \
        unzip \
        vi \
        wget \
        which \
        xz \
        zip \
    && microdnf clean all \
    && rm -rf /var/cache/dnf

# 6. Locales configuration
RUN microdnf -y install \
        glibc-langpack-en \
    && microdnf clean all \
    && rm -rf /var/cache/dnf

ENV LANG=en_US.UTF-8 \
    LC_ALL=en_US.UTF-8 \
    LC_CTYPE=en_US.UTF-8 \
    LANGUAGE=en_US.UTF-8

# 7. Shell environment
# `bind` only works interactively, and every RUN below is a non-interactive shell that
# sources this file (via /etc/profile), so guard it to keep builds free of warnings.
RUN echo 'if [[ $- == *i* ]]; then' > /etc/profile.d/eamxx-env.sh && \
    echo '  bind "\"\\e[A\": history-search-backward"' >> /etc/profile.d/eamxx-env.sh && \
    echo '  bind "\"\\e[B\": history-search-forward"' >> /etc/profile.d/eamxx-env.sh && \
    echo 'fi' >> /etc/profile.d/eamxx-env.sh

# Do NOT use `git config --system` here: it writes /etc/gitconfig, which is read by every git
# process in the container, including CI runners, and it breaks actions/checkout
# (E3SM submodules use git@ URLs; checkout does its own rewrite to https).
# Users can source this file if they REALLY want this setting.
# For devcontainer lifecycle hooks, set it in devcontainer.json
# "remoteEnv" instead: GIT_CONFIG_COUNT=1, GIT_CONFIG_KEY_0=url.https://github.com/.insteadOf,
# GIT_CONFIG_VALUE_0=git@github.com: (if adding more git settings that way, bump GIT_CONFIG_COUNT).
RUN mkdir -p /opt/share && \
    echo "git config --global url.\"https://github.com/\".insteadOf git@github.com: 2>/dev/null || true" \
    > /opt/share/gitconfig.sh

# Run a command with the full login environment (modules, SPACK_ARCH, venv) from a context
# that does not get one: `e3sm-env cmake --version`. It is also the image's ENTRYPOINT (see
# the end), so `docker run IMAGE cmake --version` goes through it too.
RUN printf '%s\n' '#!/bin/bash -l' 'exec "$@"' > /usr/local/bin/e3sm-env && \
    chmod 0755 /usr/local/bin/e3sm-env

# 8. Spack
# The spack target is the generic one for this arch, never the build host's microarch, so
# the image runs on any host of that arch. On x86_64 that is x86_64_v3 (AVX2, i.e. Haswell
# and newer), which is what the binary cache is built for; aarch64 stays fully generic, so
# the image also runs on Apple Silicon.
# profile.d, not ENV, because ENV cannot be computed at build time.
RUN case "$(uname -m)" in \
      x86_64)  target=x86_64_v3 ;; \
      aarch64) target=aarch64 ;; \
      *) echo "unsupported arch $(uname -m)" >&2; exit 1 ;; \
    esac && \
    echo "export SPACK_ARCH=linux-rhel9-${target}" > /etc/profile.d/spack-arch.sh

# Every RUN from here on starts with `. /etc/profile`, which loads /etc/profile.d (SPACK_ARCH,
# the compiler, and later the modules and venv). Not `SHELL ["/bin/bash", "-lc"]`: SHELL is
# Docker-format only, so podman/buildah (OCI format, their default) ignore it and nothing in
# /etc/profile.d would be seen. /bin/sh is bash on UBI9, so the bash syntax below still works.

ARG SPACK_VER=v1.2.2
ENV SPACK_ROOT=/spack \
    SPACK_SYSTEM_CONFIG_PATH=/spack-configuration \
    PATH=/spack/bin:$PATH

RUN . /etc/profile && git clone --depth 1 --branch "${SPACK_VER}" https://github.com/spack/spack.git /spack

COPY spack-configuration/ /spack-configuration/

# Pin every package to this arch's generic target (see above), fetch the pinned package
# recipes, bootstrap spack's solver, and trust the binary cache's signing keys -- once, here,
# so no later step or runtime user has to.
RUN . /etc/profile && sed -i "s/@SPACK_TARGET@/${SPACK_ARCH##*-}/" /spack-configuration/packages.yaml && \
    spack repo update && \
    spack bootstrap now && \
    yes | spack buildcache keys --install --trust && \
    spack clean -sdfmp

# 9. Compiler
# gcc comes from RHEL's gcc-toolset-N packages rather than being built: UBI9 carries 13
# (13.3.1), 14 and 15, so GCC_TOOLSET picks the major version and the toolset decides the
# rest. The E4S cache is built with gcc-toolset-13, so 13 gets the most cache hits. The intel image still needs gcc
# (to build what oneAPI is not used for) and gets oneAPI itself from spack.
# That gcc is lmod's core compiler, and so is gcc 13.3.1, which built what comes from the
# cache: what they build goes in Core, and what oneAPI builds appears once the
# intel-oneapi-compilers module is loaded.
# The exact compiler this image builds with is written to /etc/profile.d/compiler.sh as
# COMPILER_SPEC (e.g. gcc@13.3.1): for gcc it is only known once the toolset is installed,
# and profile.d, not ENV, because ENV cannot be computed at build time.
ARG COMPILER=gcc
ARG GCC_TOOLSET=13
ARG INTEL_VERSION=2024.1.0
ENV COMPILER=${COMPILER}

# NOTE: gcc-toolset drags in environment-modules (via scl-utils, even with weak deps off),
# whose /etc/profile.d/modules.sh overwrites Lmod's: `module` then becomes Tcl modules, which
# cannot read spack's .lua modulefiles, and nothing loads. Put Lmod's hooks back, and check.
RUN . /etc/profile && cp -p /etc/profile.d/modules.sh /etc/profile.d/modules.csh /tmp/ && \
    microdnf -y install \
        gcc-toolset-${GCC_TOOLSET}-gcc \
        gcc-toolset-${GCC_TOOLSET}-gcc-c++ \
        gcc-toolset-${GCC_TOOLSET}-gcc-gfortran \
        gcc-toolset-${GCC_TOOLSET}-libatomic-devel \
    && microdnf clean all \
    && rm -rf /var/cache/dnf && \
    mv /tmp/modules.sh /tmp/modules.csh /etc/profile.d/ && \
    grep -q /usr/share/lmod /etc/profile.d/modules.sh && \
    echo "source /opt/rh/gcc-toolset-${GCC_TOOLSET}/enable" > /etc/profile.d/gcc-toolset.sh && \
    spack compiler find --scope system /opt/rh/gcc-toolset-${GCC_TOOLSET}/root/usr/bin && \
    gcc_version="$(/opt/rh/gcc-toolset-${GCC_TOOLSET}/root/usr/bin/gcc -dumpfullversion)" && \
    spack config --scope system add "modules:default:lmod:core_compilers:[gcc@13.3.1,gcc@${gcc_version}]" && \
    case "${COMPILER}" in \
      gcc) version="${gcc_version}" ;; \
      intel-oneapi-compilers) version="${INTEL_VERSION}" ;; \
      *) echo "unsupported COMPILER=${COMPILER}" >&2; exit 1 ;; \
    esac && \
    { echo "export COMPILER_VERSION=${version}"; \
      echo "export COMPILER_SPEC=${COMPILER}@${version}"; } > /etc/profile.d/compiler.sh

# The FPGA components are stripped to satisfy security scanners. patchelf is pinned to gcc
# because otherwise spack may reuse the cache's ubuntu24.04 build of it (made with a newer
# oneAPI, and linked against a newer glibc than UBI9 has): spack only checks os/libc
# compatibility for binaries that record a libc dependency, which oneAPI-built ones do not.
RUN . /etc/profile && if [ "${COMPILER}" = "intel-oneapi-compilers" ]; then \
      spack install --fail-fast ${COMPILER_SPEC} ^patchelf %gcc && \
      rm -rf "$(spack location -i ${COMPILER_SPEC})"/compiler/*/opt/oclfpga && \
      spack gc -y && \
      spack clean -sdfmp; \
    fi

# Every E3SM-facing library below is built with "%${COMPILER_SPEC}", so it
# links against what E3SM itself is compiled with. Dependencies below those roots (zlib,
# openssl, ...) and the tools (cmake, python) may come from the cache built with gcc.
# NOTE: in spack 1.x "%compiler" binds to the one spec it follows, so it is repeated per
# root rather than given once at the end.
# NOTE: installed but deliberately NOT module-loaded until the end. Loading them puts
# spack's libcurl/libssl (cmake's deps) on LD_LIBRARY_PATH for every later RUN, where they
# shadow the system ones and break rpm/microdnf TLS.

# 10. Packages that depend only on the compiler, not on MPI or CUDA
# boost is left unconstrained: E3SM only needs its headers (ekat uses it for backtraces), so
# spack reuses the cache's gcc-built boost in every env, the intel one included (icpx uses
# gcc's libstdc++). Building it ourselves means b2, whose `install` fails intermittently with
# gcc and every time with the intel toolset.
ARG LAPACK_SPEC=openblas
RUN . /etc/profile && on="%${COMPILER_SPEC}" && \
    spack install --fail-fast cmake python@3.11 boost yaml-cpp $on ${LAPACK_SPEC} $on && \
    spack gc -y && \
    spack clean -sdfmp

ARG MPI_SPEC=openmpi@4.1.4
ARG WITH_DEBUG_TOOLS=yes
ARG WITH_CUDA=no
ARG WITH_MOAB=yes
ARG TORCH_INDEX=https://download.pytorch.org/whl/cpu
ARG TORCH_SPEC=torch

# CUDA is the one thing that still differs by arch:
#   x86_64 : spack cuda@12.4.0, as an lmod module.
#   aarch64: the NVIDIA superchips this targets (Grace Hopper/Blackwell) want CUDA 13, so it
#            comes from NVIDIA's RHEL9/SBSA repo and is exported by hand.
# NOTE: these are exported as E3SM_* rather than reusing the TORCH_*/CUPY_* names. A name
# that is also an ARG gets substituted by Docker into the instruction text before the shell
# ever runs, so an export of the same name is silently ignored.
RUN . /etc/profile && mkdir -p /etc/e3sm && \
    if [ "${WITH_CUDA}" != "yes" ]; then \
      { echo "export CUDA_FROM_SPACK=no"; \
        echo "export E3SM_CUPY_PKG="; \
        echo "export E3SM_TORCH_INDEX=${TORCH_INDEX}"; \
        echo "export E3SM_TORCH_SPEC=${TORCH_SPEC}"; } > /etc/e3sm/cuda-flavor.sh; \
    elif [ "$(uname -m)" = "aarch64" ]; then \
      { echo "export CUDA_FROM_SPACK=no"; \
        echo "export E3SM_CUPY_PKG=cupy-cuda13x"; \
        echo "export E3SM_TORCH_INDEX=https://download.pytorch.org/whl/cu130"; \
        echo "export E3SM_TORCH_SPEC=torch==2.13.0+cu130"; } > /etc/e3sm/cuda-flavor.sh; \
    else \
      { echo "export CUDA_FROM_SPACK=yes"; \
        echo "export E3SM_CUPY_PKG=cupy-cuda12x"; \
        echo "export E3SM_TORCH_INDEX=https://download.pytorch.org/whl/cu124"; \
        echo "export E3SM_TORCH_SPEC=torch==2.6.0+cu124"; } > /etc/e3sm/cuda-flavor.sh; \
    fi

# 11. CUDA. On the NVIDIA-repo path, install compiler+libraries only, NOT the "cuda-toolkit"
# meta-package: it pulls in nsight-systems, which needs GUI libs this headless image lacks.
# Fetch the GPG key with curl rather than letting `rpm --import` do it, and run rpm and
# microdnf with `env -u LD_LIBRARY_PATH`: their libcurl must not pick up a spack libssl
# that cannot verify the system CA bundle.
RUN . /etc/profile && . /etc/e3sm/cuda-flavor.sh && \
    if [ "${WITH_CUDA}" != "yes" ]; then \
      echo "skipping CUDA"; \
    elif [ "${CUDA_FROM_SPACK}" = "yes" ]; then \
      spack install --fail-fast cuda@12.4.0 && \
      spack gc -y && \
      spack clean -sdfmp; \
    else \
      curl -fsSL "https://developer.download.nvidia.com/compute/cuda/repos/rhel9/sbsa/cuda-rhel9.repo" \
          -o /etc/yum.repos.d/cuda-rhel9.repo && \
      curl -fsSL "$(sed -n 's/^gpgkey=//p' /etc/yum.repos.d/cuda-rhel9.repo | head -1)" -o /tmp/cuda.gpg && \
      env -u LD_LIBRARY_PATH rpm --import /tmp/cuda.gpg && \
      rm -f /tmp/cuda.gpg && \
      env -u LD_LIBRARY_PATH microdnf install -y cuda-compiler-13-0 cuda-libraries-13-0 cuda-libraries-devel-13-0 && \
      microdnf clean all && \
      rm -rf /var/cache/dnf; \
    fi

# 12. MPI
RUN . /etc/profile && spack install --fail-fast ${MPI_SPEC} %${COMPILER_SPEC} && \
    spack gc -y && \
    spack clean -sdfmp

# Under heavy load (e.g., a full parallel ctest run), Open MPI's mpirun can see a rank exit
# before it has recorded that rank's MPI_Finalize, and then fails a run that actually
# succeeded with "exited improperly... did not call finalize". This is a timing race inside
# Open MPI, not a bug in the test. These vars tell mpirun to accept a rank that exits with
# code 0 without that handshake; a crash or non-zero exit still fails the test.
# ORTE (OMPI 4.x) reads the first var, PRRTE (OMPI 5.x) the second; MPICH ignores both.
ENV OMPI_MCA_orte_allowed_exit_without_sync=1 \
    PRTE_MCA_prte_allowed_exit_without_sync=1

# 13. I/O libraries. Each root pinned to MPI_SPEC: the provider preference lists mpich first
# and the cache has other MPIs, so without it spack is free to pick a different MPI for them.
# NOTE: %compiler must precede ^mpi, or spack applies it to the MPI instead of the root.
RUN . /etc/profile && on="%${COMPILER_SPEC} ^${MPI_SPEC}" && \
    spack install --fail-fast hdf5+mpi $on netcdf-c+mpi $on netcdf-fortran $on parallel-netcdf $on && \
    spack gc -y && \
    spack clean -sdfmp

# MOAB, from spack: TempestRemap, Eigen and Zoltan come along as its dependencies. Its module
# exports MOAB_ROOT, like the other *_ROOT variables.
# (E3SM's moab recipe keeps Eigen on 3.x; see repos.yaml.)
RUN . /etc/profile && if [ "${WITH_MOAB}" = "yes" ]; then \
      spec="moab@5.6.0+mpi+hdf5+netcdf+pnetcdf+zoltan+eigen+tempest+fortran+shared %${COMPILER_SPEC} ^${MPI_SPEC}" && \
      spack install --fail-fast $spec && \
      spack gc -y && \
      spack clean -sdfmp; \
    fi

# 14. Debugging tools, from RHEL rather than spack: they are not linked into anything, and
# the RPMs (gdb 16, valgrind 3.26) install in seconds where spack builds took minutes.
RUN . /etc/profile && if [ "${WITH_DEBUG_TOOLS}" = "yes" ]; then \
      env -u LD_LIBRARY_PATH microdnf -y install gdb valgrind valgrind-devel && \
      microdnf clean all && \
      rm -rf /var/cache/dnf; \
    fi

# Make sure the modules for the installed packages are all available
RUN . /etc/profile && spack module lmod refresh -y --delete-tree

# Generate the profile.d script to load them all at bash startup. Module names are the spec
# names with any @version/+variant/%compiler suffix stripped.
# NOTE: the LMOD env vars silence warnings about module version swaps/reloads.
RUN . /etc/profile && mods() { echo "$*" | sed 's/[@~+%][^ ]*//g'; }; \
    { echo "source /etc/profile.d/modules.sh"; \
      echo "export MODULEPATH=/modulefiles/Core"; \
      echo "export LMOD_EXPERT=1"; \
      echo "export LMOD_DISABLE_WARNINGS=yes"; \
      echo "module purge"; \
      [ "${COMPILER}" != gcc ] && echo "module load ${COMPILER}"; \
      echo "module load python yaml-cpp cmake boost"; \
      echo "module load $(mods ${LAPACK_SPEC})"; \
      echo "module load $(mods ${MPI_SPEC})"; \
      echo "module load hdf5 netcdf-c netcdf-fortran parallel-netcdf"; \
      [ "${WITH_MOAB}" = yes ] && echo "module load moab"; \
      true; } >> /etc/profile.d/eamxx-env.sh

# CUDA isn't an lmod module on the NVIDIA-repo path, so export its env by hand there
RUN . /etc/profile && . /etc/e3sm/cuda-flavor.sh && \
    if [ "${WITH_CUDA}" != "yes" ]; then \
      echo "no CUDA env to add"; \
    elif [ "${CUDA_FROM_SPACK}" = "yes" ]; then \
      echo "module load cuda" >> /etc/profile.d/eamxx-env.sh; \
    else \
      { echo 'export CUDA_HOME=/usr/local/cuda'; \
        echo 'export PATH=$CUDA_HOME/bin:$PATH'; \
        echo 'export LD_LIBRARY_PATH=$CUDA_HOME/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}'; } >> /etc/profile.d/eamxx-env.sh; \
    fi

# 15. The default non-root user
# MPI refuses to run as root, and files written to bind mounts should not come back owned
# by root. uid/gid 1000 is the usual first host user, so mounts line up without --userns.
# Builds stay root; the image switches to this user for the python venv and stays there.
ARG USERNAME=e3sm
ARG UID=1000
ARG GID=1000
ENV E3SM_USER=${USERNAME}
RUN . /etc/profile && mkdir -p /projects/e3sm/software /projects/e3sm/data && \
    groupadd -g ${GID} ${USERNAME} && \
    useradd -m -u ${UID} -g ${GID} -s /bin/bash ${USERNAME} && \
    echo "${USERNAME} ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/${USERNAME} && \
    chmod 0440 /etc/sudoers.d/${USERNAME} && \
    chown ${USERNAME}:${USERNAME} /projects/e3sm /projects/e3sm/software /projects/e3sm/data && \
    chmod 1777 /projects/e3sm/data
# data/ is world-writable and sticky, like /tmp, so a run as another user (a CI runner) can
# still download inputdata and write baselines there when nothing is mounted over it.

# What this image is, for the smoke tests and for anyone inspecting a container
RUN . /etc/profile && { echo "E3SM_COMPILER=${COMPILER_SPEC}"; \
      echo "E3SM_MPI=${MPI_SPEC}"; \
      echo "E3SM_LAPACK=${LAPACK_SPEC}"; \
      echo "E3SM_WITH_CUDA=${WITH_CUDA}"; \
      echo "E3SM_WITH_MOAB=${WITH_MOAB}"; \
      echo "E3SM_WITH_DEBUG_TOOLS=${WITH_DEBUG_TOOLS}"; } > /etc/e3sm/image.env

# 16. Python venv, created and populated as the runtime user: doing this under root and
# later recursively changing ownership duplicates the complete environment in a new layer.
# The activation hook is guarded so the RUN that creates the venv, which sources profile.d
# before the venv exists, still works.
# cupy comes as the prebuilt wheel for the CUDA major version (cupy-cuda12x/13x), never the
# plain "cupy" sdist, which compiled from source for ~25 min; --only-binary keeps it that way.
# mpi4py goes the other way: --no-binary builds it with the mpicc loaded above, so it links
# this image's MPI. PyPI's mpi4py wheels instead dlopen whichever libmpi they find at import
# time (LD_LIBRARY_PATH, other packages in the venv), so nothing ties them to this one.
# netCDF4 stays the wheel, which bundles its own serial netCDF-C/HDF5: fine for reading and
# writing files, and the smoke test checks it reads what the spack stack writes. Parallel
# I/O from Python would need it built against spack's netcdf-c instead.
RUN . /etc/profile && echo '[ -f /projects/e3sm/software/eamxx-venv/bin/activate ] && source /projects/e3sm/software/eamxx-venv/bin/activate' >> /etc/profile.d/eamxx-env.sh

# No `ENV HOME`: docker, podman and buildah set HOME from /etc/passwd for whichever user
# runs, which is /home/e3sm for e3sm. Baked into the image, HOME would follow every other
# user too (root, `--user <uid>` such as a CI runner's), and git then fails reading the
# unreadable /home/e3sm/.gitconfig.
USER ${E3SM_USER}
RUN . /etc/profile && . /etc/e3sm/cuda-flavor.sh && \
    python3 -m venv /projects/e3sm/software/eamxx-venv && \
    source /projects/e3sm/software/eamxx-venv/bin/activate && \
    python3 -m pip install --no-cache-dir --upgrade pip && \
    python3 -m pip install --no-cache-dir --no-binary=mpi4py \
        pyyaml pylint netCDF4 psutil pybind11 mpi4py packaging xarray numpy && \
    if [ -n "${E3SM_CUPY_PKG}" ]; then \
      python3 -m pip install --no-cache-dir --only-binary=:all: "${E3SM_CUPY_PKG}"; \
    fi && \
    python3 -m pip install --no-cache-dir --extra-index-url "${E3SM_TORCH_INDEX}" "${E3SM_TORCH_SPEC}"

WORKDIR /home/${E3SM_USER}

# Every command the container is started with runs through e3sm-env, so `docker run IMAGE
# cmake --version`, `apptainer run IMAGE <cmd>`, batch launchers and anything else that hands
# the image a command get the same environment as a login shell. It execs the command, so
# signals and the exit status are the command's own. `docker exec` and `apptainer exec` never
# use the entrypoint: there it is `bash -l` or `e3sm-env <cmd>`, as before.
# With the default CMD, and with `docker run IMAGE bash -l ...`, this logs in twice. That is
# safe to repeat: lmod's `module purge` undoes the outer loads before loading them again,
# and the venv is activated again so it stays ahead of the python module on PATH (skipping
# that because VIRTUAL_ENV is already set would leave spack's python3 first). What is left
# over is a few duplicate PATH entries, in the right order.
ENTRYPOINT [ "/usr/local/bin/e3sm-env" ]
# Still --login: an interactive shell also wants what profile.d sets up but does not export
# (the history key bindings; the -dev prompt and completion).
CMD [ "/bin/bash", "--login" ]
