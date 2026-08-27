ARG BASE_TAG=base
ARG BASE_IMAGE=ghcr.io/e3sm-project/e3sm-ghci-snl
FROM ${BASE_IMAGE}:${BASE_TAG}

# Install packages in chunks, so we can tweak versions of some pkg without
# rebuilding the whole image. Hence, put "stable" pkgs first to minimize rebuild time
# NOTE: the env vars COMPILER, COMPILER_VERSION, and SPACK_ARCH are defined in the base image

# Common utilities
RUN source /spack/share/spack/setup-env.sh && \
    spack install yaml-cpp cmake %${COMPILER}@${COMPILER_VERSION} arch=${SPACK_ARCH}

# Common scientific libs (non-MPI dependent)
RUN source /spack/share/spack/setup-env.sh && \
    spack install boost netlib-lapack %${COMPILER}@${COMPILER_VERSION} arch=${SPACK_ARCH}

# MPI
RUN source /spack/share/spack/setup-env.sh && \
    spack install openmpi@4.1.4 %${COMPILER}@${COMPILER_VERSION} arch=${SPACK_ARCH}

RUN source /spack/share/spack/setup-env.sh && \
    spack install hdf5 netcdf-c+mpi netcdf-fortran parallel-netcdf %${COMPILER}@${COMPILER_VERSION} arch=${SPACK_ARCH}

# Debugging libs
RUN source /spack/share/spack/setup-env.sh && \
    spack install valgrind@3.20~mpi gdb@13.1 %${COMPILER}@${COMPILER_VERSION} arch=${SPACK_ARCH}

# Make sure the modules for the installed packages are all available
RUN source /spack/share/spack/setup-env.sh && \
    spack module lmod refresh -y --delete-tree

# Generate the profile.d script to load them all at bash startup
RUN echo "module load yaml-cpp cmake" >> /etc/profile.d/eamxx-env.sh
RUN echo "module load boost netlib-lapack" >> /etc/profile.d/eamxx-env.sh
RUN echo "module load openmpi" >> /etc/profile.d/eamxx-env.sh
RUN echo "module load hdf5 netcdf-c netcdf-fortran parallel-netcdf" >> /etc/profile.d/eamxx-env.sh
RUN echo "module load valgrind gdb" >> /etc/profile.d/eamxx-env.sh

# Install pytorch
RUN source /etc/profile.d/modules.sh        &&  \
    source /etc/profile.d/eamxx-env.sh &&  \
    python3 -m pip install                      \
            --extra-index-url https://download.pytorch.org/whl/cpu \
            torch numpy

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
RUN microdnf install -y autoconf automake libtool && \
    microdnf clean all && \
    rm -rf /var/cache/dnf

RUN . /etc/profile.d/eamxx-env.sh && \
    git clone https://github.com/e3sm-project/e3sm /tmp/e3sm && \
    cd /tmp/e3sm && . /opt/share/bash-goodies.sh && git submodule update --init cime

RUN . /etc/profile.d/eamxx-env.sh && \
    curl -fsSL "https://bitbucket.org/fathomteam/moab/raw/vijaysm/automated-build-scripts/install/install-bootstrap.sh?cb=$RANDOM" > /tmp/install-bootstrap.sh && \
    chmod u+x /tmp/install-bootstrap.sh

RUN . /etc/profile.d/eamxx-env.sh && \
    LDFLAGS="-L$HDF5_ROOT/lib" /tmp/install-bootstrap.sh    \
        --profile=e3sm                                      \
        --e3sm-root=/tmp/e3sm                               \
        --hdf5-root=$HDF5_ROOT                              \
        --netcdf-root=$NETCDF_C_ROOT                        \
        --pnetcdf-root=$PARALLEL_NETCDF_ROOT                \
        --machine=ghci-snl                                  \
        --compiler gnu                                      \
        --bootstrap-branch=vijaysm/automated-build-scripts  \
        --bootstrap-refresh --yes                           \
        --prefix=/projects/e3sm/software/moab

RUN rm -rf /tmp/e3sm && rm /tmp/install-bootstrap.sh

ENTRYPOINT []
CMD [ "/bin/bash", "--login" ]
