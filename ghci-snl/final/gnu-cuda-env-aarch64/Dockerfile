ARG BASE_TAG=UNSET
ARG BASE_IMAGE=ghcr.io/e3sm-project/e3sm-ghci-snl
FROM ${BASE_IMAGE}:${BASE_TAG}

# aarch64 equivalent of final/gnu-cuda-env, meant to run on NVIDIA aarch64
# ("superchip") systems, e.g. Grace Hopper/Grace Blackwell.
#
# NOTE: spack@0.23.1 (pinned in base/Dockerfile) only packages CUDA up to 12.6,
# so instead of `spack install cuda@...`, the toolkit below is installed straight
# from NVIDIA's official RHEL9/SBSA repository, which already offers CUDA 13.

# Install packages in chunks, so we can tweak versions of some pkg without
# rebuilding the whole image. Hence, put "stable" pkgs first to minimize rebuild time
# NOTE: the env vars COMPILER, COMPILER_VERSION, and SPACK_ARCH are defined in the base image

# Common utilities
RUN source /spack/share/spack/setup-env.sh && \
    spack install yaml-cpp cmake %${COMPILER}@${COMPILER_VERSION} arch=${SPACK_ARCH}

# Common scientific libs (non-MPI dependent)
RUN source /spack/share/spack/setup-env.sh && \
    spack install boost netlib-lapack %${COMPILER}@${COMPILER_VERSION} arch=${SPACK_ARCH}

# CUDA (NVIDIA's RHEL9/SBSA repo, since spack@0.23.1 tops out at CUDA 12.6)
# NOTE: install the compiler+libraries components only, NOT the "cuda-toolkit"
# meta-package: the latter pulls in cuda-tools -> cuda-visual-tools ->
# cuda-nsight-systems, which requires desktop/GUI libs (libOpenGL, libxcb-*,
# libxkbcommon-x11) that aren't available (and aren't wanted) in this minimal,
# headless container.
RUN curl -fsSL https://developer.download.nvidia.com/compute/cuda/repos/rhel9/sbsa/cuda-rhel9.repo \
        -o /etc/yum.repos.d/cuda-rhel9.repo && \
    rpm --import "$(sed -n 's/^gpgkey=//p' /etc/yum.repos.d/cuda-rhel9.repo | head -1)" && \
    microdnf install -y cuda-compiler-13-0 cuda-libraries-13-0 cuda-libraries-devel-13-0 && \
    microdnf clean all && \
    rm -rf /var/cache/dnf

# MPI
RUN source /spack/share/spack/setup-env.sh && \
    spack install mpich@4.1.1 %${COMPILER}@${COMPILER_VERSION} arch=${SPACK_ARCH}

# Netcdf libraries
RUN source /spack/share/spack/setup-env.sh && \
    spack install netcdf-c+mpi netcdf-fortran parallel-netcdf %${COMPILER}@${COMPILER_VERSION} arch=${SPACK_ARCH}

# Make sure the modules for the installed packages are all available
RUN source /spack/share/spack/setup-env.sh && \
    spack module lmod refresh -y --delete-tree

# Generate the profile.d script to load them all at bash startup
RUN echo "module load yaml-cpp cmake" >> /etc/profile.d/eamxx-env.sh
RUN echo "module load boost netlib-lapack" >> /etc/profile.d/eamxx-env.sh
# CUDA isn't a spack/lmod module here (see note above), so export its env by hand
RUN echo "export CUDA_HOME=/usr/local/cuda" >> /etc/profile.d/eamxx-env.sh && \
    echo "export PATH=\$CUDA_HOME/bin:\$PATH" >> /etc/profile.d/eamxx-env.sh && \
    echo "export LD_LIBRARY_PATH=\$CUDA_HOME/lib64:\$LD_LIBRARY_PATH" >> /etc/profile.d/eamxx-env.sh
RUN echo "module load mpich" >> /etc/profile.d/eamxx-env.sh
RUN echo "module load netcdf-c netcdf-fortran parallel-netcdf" >> /etc/profile.d/eamxx-env.sh

# Install numpy/cupy. Unlike x86_64, we use the prebuilt cupy-cuda13x wheel (built
# and shipped by the cupy team specifically for CUDA 13) instead of building the
# plain "cupy" sdist from source, so there's no need for the stub-linking trick.
RUN source /etc/profile.d/modules.sh        &&  \
    source /etc/profile.d/eamxx-env.sh &&  \
    python3 -m pip install numpy cupy-cuda13x

# Install pytorch
RUN source /etc/profile.d/modules.sh        &&  \
    source /etc/profile.d/eamxx-env.sh &&  \
    python3 -m pip install                      \
            --extra-index-url https://download.pytorch.org/whl/cu130 \
            torch==2.13.0+cu130

# Whomever will run the container will be able to pip install pkgs in the venv
# After all, the container is ephemeral/disposable, so there's no persistent state
RUN chmod -R a+rwX /projects/e3sm/software/eamxx-venv

# Clean up garbage packages that were only needed to BUILD other pkgs (not to USE them)
RUN source /spack/share/spack/setup-env.sh && spack gc -y

# Remove spack repo (except .git, so you can restore it) and spack buildcache (to keep image size under control)
RUN rm -rf /spack-buildcache && \
    rm -rf /spack/*

# CIME tests need a bunch of perl
RUN microdnf install -y perl

ENTRYPOINT []
CMD [ "/bin/bash", "--login" ]
