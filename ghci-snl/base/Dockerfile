FROM registry.access.redhat.com/ubi9:latest

# 1. Setup EPEL repository
RUN dnf -y install https://dl.fedoraproject.org/pub/epel/epel-release-latest-9.noarch.rpm \
    && dnf config-manager --set-disabled epel \
    && dnf clean all \
    && rm -rf /var/cache/dnf

# 2. Core Build Tools & Compilers
RUN dnf -y install \
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
    && dnf clean all \
    && rm -rf /var/cache/dnf

# 3. Scripting Runtimes (Python & Perl)
RUN dnf -y install \
        perl-devel \
        python3 \
        python3-pip \
    && dnf clean all \
    && rm -rf /var/cache/dnf

# 4. Utilities, Archiving & Environment Tools
RUN dnf -y --enablerepo=epel --allowerasing install \
        bind-utils \
        bzip2 \
        curl \
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
        wget \
        xz \
    && dnf clean all \
    && rm -rf /var/cache/dnf

# 5. Install Locales
RUN dnf -y install \
        glibc-common glibc-langpack-en glibc-locale-source && \
    dnf clean all && \
    rm -rf /var/cache/dnf

# 6. Configure Locales
RUN localedef -i en_US -f UTF-8 en_US.UTF-8 && \
    echo "LANG=en_US.UTF-8" >> /etc/locale.conf && \
    echo "LC_ALL=en_US.UTF-8" >> /etc/locale.conf

ENV LANG=en_US.UTF-8 \
    LC_ALL=en_US.UTF-8 \
    LC_CTYPE=en_US.UTF-8 \
    LANGUAGE=en_US.UTF-8

# 7. Setup SPACK
ARG SPACK_VER=v0.23.1
ENV SPACK_ROOT=/spack \
    SPACK_ARCH=linux-rhel9-x86_64 \
    PATH=/spack/bin:$PATH

RUN git clone --depth 1 --branch "${SPACK_VER}" https://github.com/spack/spack.git /spack

ADD spack-configuration/modules.yaml /spack-configuration/modules.yaml
ADD spack-configuration/packages.yaml /spack-configuration/packages.yaml
ADD spack-configuration/config.yaml /spack-configuration/config.yaml
ADD spack-configuration/mirrors.yaml /spack-configuration/mirrors.yaml

# PHASE 3: Directory Setup & User Shell Environment
RUN mkdir -p /projects/e3sm/software /projects/e3sm/data /opt/share && \
    echo 'bind "\"\\e[A\": history-search-backward"' > /opt/share/bash-goodies.sh && \
    echo 'bind "\"\\e[B\": history-search-forward"' >> /opt/share/bash-goodies.sh && \
    echo 'git config --global url."https://github.com/".insteadOf git@github.com:' >> /opt/share/bash-goodies.sh

CMD [ "/bin/bash" ]
