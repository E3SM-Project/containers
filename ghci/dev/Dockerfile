ARG BASE_TAG=UNSET
ARG BASE_IMAGE=ghcr.io/e3sm-project/e3sm-image
FROM ${BASE_IMAGE}:${BASE_TAG}

# Developer conveniences on top of a finished env image. One recipe for every variant:
# BASE_TAG picks which env this is built on, so there is nothing per-variant to maintain.
ARG VARIANT=unknown
ENV E3SM_ENV=${VARIANT}

USER root
# No SHELL instruction: it is Docker-format only, and podman/buildah (OCI format, their
# default) ignore it. Nothing here needs the login environment; the pipes that must not hide
# a failed download set pipefail themselves (/bin/sh is bash on UBI9).

# Editors and the usual navigation tools
# (less, nano, screen and zip come from the env image)
RUN microdnf -y install \
        bash-completion \
        man-db \
        openssh-clients \
        vim-enhanced \
    && microdnf clean all \
    && rm -rf /var/cache/dnf

# Build-loop tools: ninja for fast rebuilds, gdb/strace for debugging.
RUN microdnf -y install \
        gdb \
        ninja-build \
        strace \
    && microdnf clean all \
    && rm -rf /var/cache/dnf

# Interactive tools from EPEL, which the base image ships disabled.
# NOTE: tmux, htop and tree are in neither the UBI9 subset nor EPEL9; screen is the
# available multiplexer. Instead of htop, we use btop (also quite nice)
RUN microdnf -y --enablerepo=epel install \
        btop \
        bat \
        ccache \
        fzf \
        git-lfs \
        ncdu \
        ripgrep \
        tig \
    && microdnf clean all \
    && rm -rf /var/cache/dnf

# Node, so npm-installed CLIs (agent harnesses, language servers) are one command away.
# From upstream rather than the distro: the UBI9 package is node 16, which is EOL and too
# old for most of them. npm's global prefix points into $HOME so the non-root user can
# `npm i -g` without touching /opt.
ARG NODE_VERSION=24.20.0
RUN set -euo pipefail && \
    case "$(uname -m)" in \
      x86_64)  node_arch=x64 ;; \
      aarch64) node_arch=arm64 ;; \
      *) echo "unsupported arch $(uname -m)" >&2; exit 1 ;; \
    esac && \
    tarball="node-v${NODE_VERSION}-linux-${node_arch}.tar.xz" && \
    curl -fsSLO "https://nodejs.org/dist/v${NODE_VERSION}/${tarball}" && \
    curl -fsSL "https://nodejs.org/dist/v${NODE_VERSION}/SHASUMS256.txt" | grep " ${tarball}$" | sha256sum -c - && \
    mkdir -p /opt/node && \
    tar -xJf "${tarball}" -C /opt/node --strip-components=1 && \
    rm -f "${tarball}" && \
    printf '%s\n' \
      'export NPM_CONFIG_PREFIX=$HOME/.npm-global' \
      'export PATH=/opt/node/bin:$HOME/.npm-global/bin:$PATH' > /etc/profile.d/node.sh

# GitHub CLI. The el9 repo up from GitHub's own el9 repo (x86_64 and aarch64)
# upgraded gh to a versin that requires OpenPGP v6, which is NOT supported on rhel9.
# Hence, just fetch pre-compiled binaries instead, checked against the release's checksums.
ARG GH_VERSION=2.101.0
RUN set -euo pipefail && \
    ARCH=$(uname -m) && \
    case "${ARCH}" in \
      x86_64)  GH_ARCH="amd64" ;; \
      aarch64) GH_ARCH="arm64" ;; \
      *)       echo "Unsupported architecture: ${ARCH}" && exit 1 ;; \
    esac && \
    release="https://github.com/cli/cli/releases/download/v${GH_VERSION}" && \
    tarball="gh_${GH_VERSION}_linux_${GH_ARCH}.tar.gz" && \
    curl -fsSLO "${release}/${tarball}" && \
    curl -fsSL "${release}/gh_${GH_VERSION}_checksums.txt" | grep " ${tarball}$" | sha256sum -c - && \
    tar -xzf "${tarball}" --strip-components=1 -C /usr/local && \
    rm -f "${tarball}"

# Shell ergonomics. Loaded last so it wins over the env setup from the stages below.
RUN printf '%s\n' \
    'if [[ $- == *i* ]]; then' \
    '  [ -f /usr/share/bash-completion/bash_completion ] && . /usr/share/bash-completion/bash_completion' \
    '  [ -f /usr/share/git-core/contrib/completion/git-prompt.sh ] && . /usr/share/git-core/contrib/completion/git-prompt.sh' \
    '  export GIT_PS1_SHOWDIRTYSTATE=1' \
    '  PS1="\[\e[1;32m\]\u@${E3SM_ENV:-e3sm}\[\e[0m\]:\[\e[1;34m\]\w\[\e[0;33m\]$(__git_ps1 " (%s)" 2>/dev/null)\[\e[0m\]\$ "' \
    '  alias ll="ls -alFh"' \
    '  alias ..="cd .."' \
    '  shopt -s checkwinsize histappend' \
    '  export HISTSIZE=100000 HISTFILESIZE=100000 HISTCONTROL=ignoreboth' \
    '  export EDITOR=vim PAGER=less' \
    'fi' > /etc/profile.d/e3sm-dev.sh

# A predictable place to clone and build, on the same volume as the rest of /projects
RUN mkdir -p /projects/e3sm/work && \
    chown -R ${E3SM_USER}:${E3SM_USER} /projects/e3sm/work && \
    ln -sfn /projects/e3sm/work /home/${E3SM_USER}/work

# Pre-create the dirs a dev container typically mounts volumes onto. A named volume
# mounted at a path that does NOT exist in the image is created root-owned, and then the
# non-root user cannot write to it.
RUN mkdir -p /home/${E3SM_USER}/.cache/ccache \
             /home/${E3SM_USER}/.config \
             /home/${E3SM_USER}/.claude \
             /home/${E3SM_USER}/.codex \
             /home/${E3SM_USER}/.copilot \
             /home/${E3SM_USER}/.local/share/opencode && \
    chown -R ${E3SM_USER}:${E3SM_USER} /home/${E3SM_USER}

# A bind-mounted repo is owned by the host's uid, which need not be ours; without this git
# refuses to operate on it ("dubious ownership"). Trust that only where checkouts are meant
# to go, not everywhere ('*'): git >= 2.46 (UBI9 has 2.52) reads a trailing /* as "anything
# under this path", which covers the checkout and every nested submodule, each of which git
# checks separately. ~/work is a symlink to it, and git compares the resolved path. A
# checkout elsewhere needs its own `git config --global --add safe.directory <path>`.
RUN git config --system --add safe.directory '/projects/e3sm/work/*'

# On a Linux host whose uid is not 1000, Dev Containers' updateRemoteUserUID gives e3sm the
# host user's uid/gid, but only re-owns $HOME: the venv and the /projects/e3sm dirs stay
# uid 1000, so `pip install` and creating anything next to the checkout fail.
# e3sm-fix-ownership hands them to whoever runs it; the devcontainer example calls it from
# postCreateCommand. Not done unconditionally (or by moving the venv into $HOME, which the
# remap would then re-own): re-owning the venv copies all of it, 1-6 GB, into the
# container's writable layer. With uid 1000 (macOS, Windows, most single-user Linux hosts)
# nothing needs changing and it returns at once. It checks every file in the venv, not just
# the top dir, so a run that was interrupted is finished by the next one. Only the dirs
# themselves under /projects/e3sm, never what is in data/ and work/: those are the user's
# bind mounts.
RUN printf '%s\n' \
      '#!/bin/bash' \
      'set -euo pipefail' \
      'uid=$(id -u) gid=$(id -g)' \
      'venv=/projects/e3sm/software/eamxx-venv' \
      'dirs=(/projects/e3sm /projects/e3sm/software /projects/e3sm/data /projects/e3sm/work)' \
      'if [ -z "$(find "${dirs[@]}" -maxdepth 0 ! -uid "$uid" -print -quit)" ] &&' \
      '   [ -z "$(find "$venv" ! -uid "$uid" -print -quit)" ]; then' \
      '    exit 0' \
      'fi' \
      'echo "e3sm-fix-ownership: handing $venv and /projects/e3sm to uid $uid (once per container; can take a minute)" >&2' \
      'sudo chown "$uid:$gid" "${dirs[@]}"' \
      'sudo chown -R -h "$uid:$gid" "$venv"' > /usr/local/bin/e3sm-fix-ownership && \
    chmod 0755 /usr/local/bin/e3sm-fix-ownership

# The image's CIME machine (see /projects/e3sm/cime/enable.sh), so create_newcase and
# create_test need no --machine in a dev container. Only in e3sm's own home: a foreign HOME
# (Apptainer brings the host's) is never written to; source the script there to opt in.
RUN printf '%s\n' \
    'if [ "$HOME" = "/home/${E3SM_USER:-e3sm}" ]; then . /projects/e3sm/cime/enable.sh; fi' \
    > /etc/profile.d/e3sm-cime-machine.sh

# Where the per-user installers below put their binaries
RUN printf '%s\n' \
    'export PATH=$HOME/.local/bin:$HOME/.opencode/bin:$PATH' > /etc/profile.d/user-tools.sh

USER ${E3SM_USER}

# uv, and the coding agents. Each comes from its own upstream installer and lands in
# $HOME, so `uv self update` / `claude update` / `opencode upgrade` / `codex --upgrade`
# all work inside a running container without root. Deliberately unpinned: pinning would
# defeat the self-update these are installed for.
RUN set -o pipefail && curl -LsSf https://astral.sh/uv/install.sh | sh
RUN set -o pipefail && curl -fsSL https://claude.ai/install.sh | bash
RUN set -o pipefail && curl -fsSL https://opencode.ai/install | bash
RUN set -o pipefail && curl -fsSL https://chatgpt.com/codex/install.sh | sh
RUN set -o pipefail && curl -fsSL https://gh.io/copilot-install | bash

WORKDIR /projects/e3sm/work

# The env image's entrypoint and default command (see there). Setting ENTRYPOINT resets the
# inherited CMD, so both are spelled out rather than half-inherited.
ENTRYPOINT [ "/usr/local/bin/e3sm-env" ]
CMD [ "/bin/bash", "--login" ]
