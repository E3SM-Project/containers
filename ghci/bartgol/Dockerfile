ARG BASE_TAG=gnu-cpu-env-dev-pr-48
ARG BASE_IMAGE=ghcr.io/e3sm-project/e3sm-ghci
FROM ${BASE_IMAGE}:${BASE_TAG}

USER root

# SNL certs
COPY snl-ca-bundle.crt /etc/pki/ca-trust/source/anchors/snl-ca-bundle.crt
RUN update-ca-trust extract
ENV NODE_EXTRA_CA_CERTS=/etc/pki/ca-trust/source/anchors/snl-ca-bundle.crt

# pinentry stuff (for gpg)
RUN microdnf -y install \
        pinentry \
        pinentry-tty \
    && microdnf clean all \
    && rm -rf /var/cache/dnf

# Trilinos
RUN cd /projects/e3sm/software/ && mkdir trilinos && cd trilinos && \
    git clone https://github.com/trilinos/Trilinos.git source

COPY --chmod=755 do-cmake-trilinos.sh /projects/e3sm/software/trilinos/build/do-cmake-trilinos.sh
RUN source /etc/profile.d/eamxx-env.sh && \
    cd /projects/e3sm/software/trilinos/build/ && \
    ./do-cmake-trilinos.sh && make -j install && \
    cd ../ && rm -rf source build

# Install lazygit
RUN curl -sL https://copr.fedorainfracloud.org/coprs/atim/lazygit/repo/epel-9/atim-lazygit-epel-9.repo \
    -o /etc/yum.repos.d/atim-lazygit-epel-9.repo && \
    microdnf install -y lazygit

# bartgol gitconfig
COPY gitconfig /home/e3sm/.gitconfig

USER ${E3SM_USER}

ENTRYPOINT []
CMD [ "/bin/bash", "--login" ]
