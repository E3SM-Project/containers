FROM registry.access.redhat.com/ubi9-minimal:latest

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

# 3. Core build tools & compilers
RUN microdnf -y install \
        binutils \
        bzip2-devel \
        diffutils \
        file \
        gcc \
        gcc-c++ \
        gcc-gfortran \
        glibc-devel \
        make \
        ncurses-devel \
        patch \
        pkgconfig \
    && microdnf clean all \
    && rm -rf /var/cache/dnf

# 4. Scripting runtimes (python & perl)
RUN microdnf -y install \
        perl-devel \
        python3 \
        python3-pip \
    && microdnf clean all \
    && rm -rf /var/cache/dnf

# 5. Utilities, archiving & environment tools
# NOTE: which, bc, findutils and rsync are not in ubi9-minimal, and build systems assume
# they exist -- CIME and configure scripts call `which nvcc`, `which mpicc` and friends.
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
        Lmod \
        procps \
        rsync \
        shadow-utils \
        sudo \
        tar \
        unzip \
        vi \
        wget \
        which \
        xz \
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

# 7. Setup SPACK
ARG SPACK_VER=v0.23.1
ENV SPACK_ROOT=/spack \
    SPACK_SYSTEM_CONFIG_PATH=/spack-configuration \
    PATH=/spack/bin:$PATH

# Read the arch off the build machine (images are always built natively for their target),
# so no caller has to pass it and no tag has to carry it. Pin the GENERIC target rather
# than let spack detect the builder's microarch, so the image runs on any host of that arch.
# profile.d, not ENV, because ENV cannot be computed at build time.
RUN echo "export SPACK_ARCH=linux-rhel9-$(uname -m)" > /etc/profile.d/spack-arch.sh

SHELL ["/bin/bash", "-lc"]

RUN git clone --depth 1 --branch "${SPACK_VER}" https://github.com/spack/spack.git /spack

ADD spack-configuration/modules.yaml /spack-configuration/modules.yaml
ADD spack-configuration/packages.yaml /spack-configuration/packages.yaml
ADD spack-configuration/config.yaml /spack-configuration/config.yaml
ADD spack-configuration/mirrors.yaml /spack-configuration/mirrors.yaml

# 8. Setup project directory & user shell environment
RUN mkdir -p /projects/e3sm/software /projects/e3sm/data

# `bind` only works interactively, and every RUN below is a non-interactive login shell
# that sources this file, so guard it to keep builds free of warnings.
RUN echo 'if [[ $- == *i* ]]; then' > /etc/profile.d/eamxx-env.sh && \
    echo '  bind "\"\\e[A\": history-search-backward"' >> /etc/profile.d/eamxx-env.sh && \
    echo '  bind "\"\\e[B\": history-search-forward"' >> /etc/profile.d/eamxx-env.sh && \
    echo 'fi' >> /etc/profile.d/eamxx-env.sh

# System-wide rather than a `git config --global` run from profile.d, so it also applies to
# non-login shells: devcontainer lifecycle hooks and anything under `sh -c` never source
# /etc/profile.d, and E3SM's submodules use git@ URLs.
RUN git config --system url."https://github.com/".insteadOf git@github.com:

# Run a command with the full login environment (modules, SPACK_ARCH, venv) from a context
# that does not get one: `e3sm-env cmake --version`.
RUN printf '%s\n' '#!/bin/bash -l' 'exec "$@"' > /usr/local/bin/e3sm-env && \
    chmod 0755 /usr/local/bin/e3sm-env

# 9. Default non-root user
# MPI refuses to run as root, and files written to bind mounts should not come back owned
# by root. uid/gid 1000 is the usual first host user, so mounts line up without --userns.
# Builds stay root; the final images switch to this user at the end.
ARG USERNAME=e3sm
ARG UID=1000
ARG GID=1000
ENV E3SM_USER=${USERNAME}
RUN groupadd -g ${GID} ${USERNAME} && \
    useradd -m -u ${UID} -g ${GID} -s /bin/bash ${USERNAME} && \
    echo "${USERNAME} ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/${USERNAME} && \
    chmod 0440 /etc/sudoers.d/${USERNAME} && \
    chown -R ${USERNAME}:${USERNAME} /projects/e3sm

# --login, so /etc/profile.d (SPACK_ARCH, and the module env added downstream) applies
CMD [ "/bin/bash", "--login" ]
