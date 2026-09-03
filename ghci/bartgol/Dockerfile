ARG BASE_TAG=gnu-cpu-env-dev
ARG BASE_IMAGE=ghcr.io/e3sm-project/e3sm-ghci
FROM ${BASE_IMAGE}:${BASE_TAG}

USER root

# SNL certs
COPY snl-ca-bundle.crt /etc/pki/ca-trust/source/anchors/snl-ca-bundle.crt
RUN update-ca-trust extract
ENV NODE_EXTRA_CA_CERTS=/etc/pki/ca-trust/source/anchors/snl-ca-bundle.crt

# Install lazygit
RUN curl -sL https://copr.fedorainfracloud.org/coprs/atim/lazygit/repo/epel-9/atim-lazygit-epel-9.repo \
    -o /etc/yum.repos.d/atim-lazygit-epel-9.repo && \
    microdnf install -y lazygit

# Install parmetis
RUN cd /spack && git reset --hard HEAD

RUN source /etc/profile.d/eamxx-env.sh source /spack/share/spack/setup-env.sh && \
    spack install --fail-fast parmetis %${COMPILER}@${COMPILER_VERSION} arch=${SPACK_ARCH} && \
    spack gc -y && \
    spack clean -a

RUN echo "module load parmetis" >> /etc/profile.d/eamxx-env.sh

RUN rm -rf /spack-buildcache && \
    rm -rf /spack/*

USER ${E3SM_USER}

# Trilinos
RUN cd /projects/e3sm/software/ && mkdir trilinos && cd trilinos && \
    git clone --depth 1 --single-branch -b develop https://github.com/trilinos/Trilinos.git source

COPY --chown=e3sm:e3sm --chmod=755 do-cmake-trilinos.sh /projects/e3sm/software/trilinos/build/do-cmake-trilinos.sh
RUN source /etc/profile.d/eamxx-env.sh && \
    cd /projects/e3sm/software/trilinos/build/ && \
    ./do-cmake-trilinos.sh && make -j12 install && \
    cd ../ && rm -rf source build

# bartgol gitconfig
COPY --chown=e3sm:e3sm gitconfig /home/e3sm/.gitconfig

ENTRYPOINT []
CMD [ "/bin/bash", "--login" ]
