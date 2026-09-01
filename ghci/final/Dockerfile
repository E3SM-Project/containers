ARG BASE_TAG=UNSET
ARG BASE_IMAGE=ghcr.io/e3sm-project/e3sm-ghci
FROM ${BASE_IMAGE}:${BASE_TAG}

# One recipe for every env variant. The variants themselves (which args each one sets) are
# the matrix in .github/workflows/ghci.yaml; the defaults below are the gnu-cpu-env values.
# Spack picks the target up from SPACK_ARCH, which the base image derives from the machine
# it is built on, so nothing here is parameterized by arch.
ARG MPI_SPEC=openmpi@4.1.4
ARG LAPACK_SPEC=netlib-lapack
ARG DEBUG_SPECS="valgrind@3.20~mpi gdb@13.1"
ARG WITH_CUDA=no
ARG WITH_MOAB=yes
ARG TORCH_INDEX=https://download.pytorch.org/whl/cpu
ARG TORCH_SPEC=torch

# CUDA is the one thing that still differs by arch:
#   x86_64 : spack cuda@12.4.0, as an lmod module.
#   aarch64: spack@0.23.1 tops out at CUDA 12.6, but the NVIDIA superchips this targets
#            (Grace Hopper/Blackwell) want CUDA 13, so it comes from NVIDIA's RHEL9/SBSA
#            repo and is exported by hand. Drop this split once spack packages CUDA 13.
# NOTE: these are exported as E3SM_* rather than reusing the TORCH_*/CUPY_* names. A name
# that is also an ARG gets substituted by Docker into the instruction text before the shell
# ever runs, so a profile.d export of the same name is silently ignored.
RUN if [ "${WITH_CUDA}" != "yes" ]; then \
      { echo "export CUDA_FROM_SPACK=no"; \
        echo "export E3SM_CUPY_PKG="; \
        echo "export E3SM_TORCH_INDEX=${TORCH_INDEX}"; \
        echo "export E3SM_TORCH_SPEC=${TORCH_SPEC}"; } > /etc/profile.d/cuda-flavor.sh; \
    elif [ "$(uname -m)" = "aarch64" ]; then \
      { echo "export CUDA_FROM_SPACK=no"; \
        echo "export E3SM_CUPY_PKG=cupy-cuda13x"; \
        echo "export E3SM_TORCH_INDEX=https://download.pytorch.org/whl/cu130"; \
        echo "export E3SM_TORCH_SPEC=torch==2.13.0+cu130"; } > /etc/profile.d/cuda-flavor.sh; \
    else \
      { echo "export CUDA_FROM_SPACK=yes"; \
        echo "export E3SM_CUPY_PKG=cupy"; \
        echo "export E3SM_TORCH_INDEX=https://download.pytorch.org/whl/cu124"; \
        echo "export E3SM_TORCH_SPEC=torch==2.6.0+cu124"; } > /etc/profile.d/cuda-flavor.sh; \
    fi

# Install packages in chunks, so we can tweak versions of some pkg without
# rebuilding the whole image. Hence, put "stable" pkgs first to minimize rebuild time
# NOTE: the env vars COMPILER, COMPILER_VERSION, and SPACK_ARCH are defined in the base image

# LAPACK provider. yaml-cpp, cmake and boost come from the compiler image, which every
# env shares, so they are not rebuilt here.
RUN source /spack/share/spack/setup-env.sh && \
    spack install ${LAPACK_SPEC} %${COMPILER}@${COMPILER_VERSION} arch=${SPACK_ARCH}

# CUDA. On the NVIDIA-repo path, install compiler+libraries only, NOT the "cuda-toolkit"
# meta-package: it pulls in nsight-systems, which needs GUI libs this headless image lacks.
# Fetch the GPG key with curl rather than letting `rpm --import` do it: rpm uses its own
# libcurl, which picks up spack's libssl off LD_LIBRARY_PATH and then cannot verify the
# system CA bundle. Same reason for `env -u LD_LIBRARY_PATH` on rpm and microdnf.
RUN if [ "${WITH_CUDA}" != "yes" ]; then \
      echo "skipping CUDA"; \
    elif [ "${CUDA_FROM_SPACK}" = "yes" ]; then \
      source /spack/share/spack/setup-env.sh && \
      spack install cuda@12.4.0 %${COMPILER}@${COMPILER_VERSION} arch=${SPACK_ARCH}; \
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

# MPI
RUN source /spack/share/spack/setup-env.sh && \
    spack install ${MPI_SPEC} %${COMPILER}@${COMPILER_VERSION} arch=${SPACK_ARCH}

# I/O libraries
RUN source /spack/share/spack/setup-env.sh && \
    spack install hdf5 netcdf-c+mpi netcdf-fortran parallel-netcdf %${COMPILER}@${COMPILER_VERSION} arch=${SPACK_ARCH}

# MOAB's "zoltan" TPL, as fetched by the vendor install-bootstrap.sh script further down
# from its default (circa-2013) dist tarball mirror, ships a bundled config.guess/
# config.sub that predates the aarch64 GNU triplet, so its ./configure fails immediately on
# aarch64 -- and the vendor script has no remediation pattern that recognizes that failure,
# so it just aborts. We can't patch that third-party script, so work around it here
# instead: pre-build zoltan via spack (whose package.py always reruns autoreconf,
# regenerating a current, aarch64-aware config.guess/config.sub) while spack is still
# available in this image, matching the same version/MPI/link flags the vendor script would
# have used itself. The vendor script's own TPL-reuse feature (REUSE_TPLS=yes by default)
# will find this already built at the path it expects and skip building zoltan itself. Done
# for every arch (not just aarch64, which is the only one that needs it) to keep this
# recipe simple: on x86_64 the vendor script would have built the same thing.
RUN if [ "${WITH_MOAB}" = "yes" ]; then \
      source /spack/share/spack/setup-env.sh && \
      spack install --reuse zoltan@3.901+mpi+fortran~shared %${COMPILER}@${COMPILER_VERSION} arch=${SPACK_ARCH} ^${MPI_SPEC} && \
      mkdir -p /projects/e3sm/software/moab/tpls && \
      ln -s "$(spack location -i zoltan@3.901 %${COMPILER}@${COMPILER_VERSION} arch=${SPACK_ARCH} ^${MPI_SPEC})" /projects/e3sm/software/moab/tpls/zoltan; \
    fi

# Debugging libs
RUN if [ -n "${DEBUG_SPECS}" ]; then \
      source /spack/share/spack/setup-env.sh && \
      spack install ${DEBUG_SPECS} %${COMPILER}@${COMPILER_VERSION} arch=${SPACK_ARCH}; \
    fi

# Make sure the modules for the installed packages are all available
RUN source /spack/share/spack/setup-env.sh && \
    spack module lmod refresh -y --delete-tree

# Generate the profile.d script to load them all at bash startup. Module names are the spec
# names with any @version/+variant/%compiler suffix stripped.
RUN mods() { echo "$*" | sed 's/[@~+%][^ ]*//g'; }; \
    { echo "module load yaml-cpp cmake boost"; \
      echo "module load $(mods ${LAPACK_SPEC})"; \
      echo "module load $(mods ${MPI_SPEC})"; \
      echo "module load hdf5 netcdf-c netcdf-fortran parallel-netcdf"; \
      [ -n "${DEBUG_SPECS}" ] && echo "module load $(mods ${DEBUG_SPECS})"; \
      true; } >> /etc/profile.d/eamxx-env.sh

# CUDA isn't an lmod module on the NVIDIA-repo path, so export its env by hand there
RUN if [ "${WITH_CUDA}" != "yes" ]; then \
      echo "no CUDA env to add"; \
    elif [ "${CUDA_FROM_SPACK}" = "yes" ]; then \
      echo "module load cuda" >> /etc/profile.d/eamxx-env.sh; \
    else \
      { echo 'export CUDA_HOME=/usr/local/cuda'; \
        echo 'export PATH=$CUDA_HOME/bin:$PATH'; \
        echo 'export LD_LIBRARY_PATH=$CUDA_HOME/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}'; } >> /etc/profile.d/eamxx-env.sh; \
    fi

# Install numpy, and cupy where there is a GPU to use it. The plain "cupy" sdist builds
# from source and must link against the driver stubs; "cupy-cuda13x" is a prebuilt wheel.
RUN source /etc/profile.d/modules.sh && \
    source /etc/profile.d/eamxx-env.sh && \
    if [ "${WITH_CUDA}" != "yes" ]; then \
      python3 -m pip install numpy; \
    elif [ "${CUDA_FROM_SPACK}" = "yes" ]; then \
      LIBRARY_PATH="$CUDA_HOME/lib64/stubs:$LIBRARY_PATH" python3 -m pip install numpy "${E3SM_CUPY_PKG}"; \
    else \
      python3 -m pip install numpy "${E3SM_CUPY_PKG}"; \
    fi

# Install pytorch. The CUDA flavor file overrides TORCH_* on the NVIDIA-repo path.
RUN source /etc/profile.d/cuda-flavor.sh && \
    source /etc/profile.d/modules.sh && \
    source /etc/profile.d/eamxx-env.sh && \
    python3 -m pip install --extra-index-url "${E3SM_TORCH_INDEX}" "${E3SM_TORCH_SPEC}"

# Whomever will run the container will be able to pip install pkgs in the venv
# After all, the container is ephemeral/disposable, so there's no persistent state
RUN chmod -R a+rwX /projects/e3sm/software/eamxx-venv

# Clean up garbage packages that were only needed to BUILD other pkgs (not to USE them)
RUN source /spack/share/spack/setup-env.sh && \
    spack gc -y

# Remove spack repo (except .git, so you can restore it) and spack buildcache (to keep image size under control)
RUN rm -rf /spack-buildcache && \
    rm -rf /spack/*

# CIME tests need a bunch of perl
RUN microdnf install -y perl && \
    microdnf clean all && \
    rm -rf /var/cache/dnf

# Install MOAB
RUN if [ "${WITH_MOAB}" = "yes" ]; then \
      microdnf install -y autoconf automake libtool && \
      microdnf clean all && \
      rm -rf /var/cache/dnf; \
    fi

# NOTE: --machine is E3SM's CIME machine name (config_machines.xml), not this image's
# name; it stays "ghci-snl" until E3SM renames the machine.
RUN if [ "${WITH_MOAB}" = "yes" ]; then \
      . /etc/profile.d/eamxx-env.sh && \
      git clone https://github.com/e3sm-project/e3sm /tmp/e3sm && \
      cd /tmp/e3sm && git submodule update --init cime && \
      curl -fsSL "https://bitbucket.org/fathomteam/moab/raw/vijaysm/automated-build-scripts/install/install-bootstrap.sh?cb=$RANDOM" > /tmp/install-bootstrap.sh && \
      chmod u+x /tmp/install-bootstrap.sh && \
      LDFLAGS="-L$HDF5_ROOT/lib" /tmp/install-bootstrap.sh         \
          --profile=e3sm                                          \
          --e3sm-root=/tmp/e3sm                                   \
          --hdf5-root=$HDF5_ROOT                                  \
          --netcdf-root=$NETCDF_C_ROOT                            \
          --pnetcdf-root=$PARALLEL_NETCDF_ROOT                    \
          --machine=ghci-snl                                      \
          --compiler gnu                                          \
          --bootstrap-branch=vijaysm/automated-build-scripts      \
          --bootstrap-refresh --yes                               \
          --prefix=/projects/e3sm/software/moab && \
      rm -rf /tmp/e3sm /tmp/install-bootstrap.sh; \
    fi

# Done with the flavor file; what it selected is already baked into eamxx-env.sh
RUN rm -f /etc/profile.d/cuda-flavor.sh

# Hand the runtime over to the non-root user created in the base image
RUN chown -R ${E3SM_USER}:${E3SM_USER} /projects/e3sm
USER ${E3SM_USER}
ENV HOME=/home/${E3SM_USER}
WORKDIR ${HOME}

ENTRYPOINT []
CMD [ "/bin/bash", "--login" ]
