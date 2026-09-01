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
RUN microdnf -y --enablerepo=epel install \
        bind-utils \
        bzip2 \
        curl-minimal \
        git \
        gzip \
        hostname \
        iputils \
        jq \
        Lmod \
        procps \
        sudo \
        tar \
        unzip \
        vim \
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
# Override at build time (e.g. --build-arg SPACK_ARCH=linux-rhel9-aarch64) for aarch64 images
ARG SPACK_ARCH=linux-rhel9-x86_64
ENV SPACK_ROOT=/spack \
    SPACK_ARCH=${SPACK_ARCH} \
    SPACK_SYSTEM_CONFIG_PATH=/spack-configuration \
    PATH=/spack/bin:$PATH

RUN git clone --depth 1 --branch "${SPACK_VER}" https://github.com/spack/spack.git /spack

ADD spack-configuration/modules.yaml /spack-configuration/modules.yaml
ADD spack-configuration/packages.yaml /spack-configuration/packages.yaml
ADD spack-configuration/config.yaml /spack-configuration/config.yaml
ADD spack-configuration/mirrors.yaml /spack-configuration/mirrors.yaml

# 8. Setup project directory & user shell environment
RUN mkdir -p /projects/e3sm/software /projects/e3sm/data

RUN echo 'bind "\"\\e[A\": history-search-backward"' > /etc/profile.d/eamxx-env.sh && \
    echo 'bind "\"\\e[B\": history-search-forward"' >> /etc/profile.d/eamxx-env.sh && \
    echo 'git config --global url."https://github.com/".insteadOf git@github.com:' >> /etc/profile.d/eamxx-env.sh

CMD [ "/bin/bash" ]
