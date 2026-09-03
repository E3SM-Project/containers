ARG BASE_TAG=base
ARG BASE_IMAGE=ghcr.io/e3sm-project/e3sm-ghci
FROM ${BASE_IMAGE}:${BASE_TAG}

# Must pass these build args to pick compiler/compiler-version
ARG COMPILER
ARG COMPILER_VERSION

# Make these available as env vars
ENV COMPILER=${COMPILER}
ENV COMPILER_VERSION=${COMPILER_VERSION}

# Check if COMPILER and COMPILER_VERSION are set; if not, error out
RUN if [ -z "$COMPILER" ]; then echo "Error: COMPILER must be set." && exit 1; fi && \
    if [ -z "$COMPILER_VERSION" ]; then echo "Error: COMPILER_VERSION must be set." && exit 1; fi

# Needed for "source" to work, and for SPACK_ARCH from the base image's profile.d
SHELL ["/bin/bash", "-lc"]

# Unlike gcc, for intel, the spack package (and subsequent module) name and the name
# of the compiler to be used in subsequent spack install commands differ.
# Namely, the pkg name is 'intel-oneapi-compilers', while the compiler name is 'oneapi'.
RUN if [ "${COMPILER}" = "oneapi" ]; then \
      echo "export COMPILER_MODULE_NAME=intel-oneapi-compilers" >> /etc/profile.d/compiler_name.sh; \
    else \
      echo "export COMPILER_MODULE_NAME=${COMPILER}" >> /etc/profile.d/compiler_name.sh; \
    fi

# Make spack discover the system compilers in /usr/bin
RUN source /spack/share/spack/setup-env.sh && \
    spack compiler add /usr/bin

#Install the compiler we want using spack
RUN source /spack/share/spack/setup-env.sh && source /etc/profile.d/compiler_name.sh && \
    spack install ${COMPILER_MODULE_NAME}@${COMPILER_VERSION} arch=${SPACK_ARCH} && \
    # If this is an Intel build, strip out the unused FPGA host directory to eliminate SNL security flags
    if [ "${COMPILER}" = "oneapi" ]; then \
        echo "Stripping unused FPGA components to satisfy security scanners..." && \
        COMPILER_ROOT="$(spack location -i ${COMPILER_MODULE_NAME}@${COMPILER_VERSION})" && \
        rm -rf ${COMPILER_ROOT}/compiler/latest/opt/oclfpga \
               ${COMPILER_ROOT}/compiler/*/opt/oclfpga; \
    fi

# Create the eamxx environment setup script with Module settings
# NOTE: the LMOD env vars are to silence warning regarding module version swap/reload.
#       that happens b/c the compiler is built against gcc@11.5.0, but downstream packages
#       are built against ${COMPILER}@${COMPILER_VERSION}, which may cause some modules
#       to be re-installed with diff compiler, and lmod to reload the proper version.
#       This is 100% fine, but would produce rather lengthy warnings.
RUN source /etc/profile.d/compiler_name.sh && \
    echo "source /etc/profile.d/modules.sh" >> /etc/profile.d/eamxx-env.sh &&  \
    echo "export MODULEPATH=/modulefiles/${SPACK_ARCH}/Core" >> /etc/profile.d/eamxx-env.sh && \
    echo "export LMOD_EXPERT=1" >> /etc/profile.d/eamxx-env.sh && \
    echo "export LMOD_DISABLE_WARNINGS=yes" >> /etc/profile.d/eamxx-env.sh && \
    echo "module purge" >> /etc/profile.d/eamxx-env.sh && \
    echo "module load ${COMPILER_MODULE_NAME}" >> /etc/profile.d/eamxx-env.sh

RUN source /spack/share/spack/setup-env.sh && source /etc/profile.d/compiler_name.sh && \
    COMPILER_ROOT=$(spack location -i ${COMPILER_MODULE_NAME}@${COMPILER_VERSION}) && \
    spack compiler find ${COMPILER_ROOT} ${COMPILER_ROOT}/* ${COMPILER_ROOT}/*/*

# We tell spack that ALL pkgs from now on must be built with ${COMPILER}@${COMPILER_VERSION}.
# But there's a catch! While Spack is smart enough to not rebuild the compiler itself (it'd be a cyclic dep),
# the new oneapi compilers have a pkg name that DIFFERS from the compiler name, so spack
# would NOT catch that, and attempt to rebuild intel-oneapi-compilers with oneapi.
# To prevent that, we ALREADY added a special entry package:intel-oneapi-compilers:compiler:[gcc@11.5.0]
# in the packages.yaml we copied into /spack-configuration during the base image
RUN source /spack/share/spack/setup-env.sh && \
    spack config add "packages:all:compiler:[${COMPILER}@${COMPILER_VERSION}]"

# Packages that depend only on the compiler, not on the MPI/CUDA/LAPACK choices the env
# images make. Built here so every env built on this image reuses them instead of each
# rebuilding cmake and boost from source.
# NOTE: installed but deliberately NOT module-loaded here. Loading them puts spack's
# libcurl/libssl (cmake's deps) on LD_LIBRARY_PATH for every later RUN, where they shadow
# the system ones and break rpm/microdnf TLS. The env images load them at the end, once
# the package-manager steps are done.
RUN source /spack/share/spack/setup-env.sh && \
    spack install yaml-cpp cmake boost %${COMPILER}@${COMPILER_VERSION} arch=${SPACK_ARCH}

# Install python, setup virtual env, and install common pip packages
RUN source /spack/share/spack/setup-env.sh && \
    spack install --fresh python@3.11 %${COMPILER}@${COMPILER_VERSION} arch=${SPACK_ARCH}
RUN echo "module load python" >> /etc/profile.d/eamxx-env.sh

RUN source /etc/profile.d/eamxx-env.sh && \
    cd /projects/e3sm/software && python3 -m  venv eamxx-venv
RUN echo "source /projects/e3sm/software/eamxx-venv/bin/activate" >> /etc/profile.d/eamxx-env.sh

RUN source /etc/profile.d/eamxx-env.sh &&  \
    python3 -m pip install --upgrade pip

RUN source /etc/profile.d/eamxx-env.sh &&       \
    python3 -m pip install                      \
            pyyaml pylint netCDF4 psutil        \
            pybind11 mpi4py packaging xarray

ENTRYPOINT []

CMD [ "/bin/bash", "--login" ]
