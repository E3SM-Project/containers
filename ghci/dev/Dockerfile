ARG BASE_TAG=UNSET
ARG BASE_IMAGE=ghcr.io/e3sm-project/e3sm-ghci
FROM ${BASE_IMAGE}:${BASE_TAG}

# Developer conveniences on top of a finished env image. One recipe for every variant:
# BASE_TAG picks which env this is built on, so there is nothing per-variant to maintain.
ARG VARIANT=unknown
ENV E3SM_ENV=${VARIANT}

USER root

# Editors and the usual navigation tools
RUN microdnf -y install \
        bash-completion \
        less \
        man-db \
        nano \
        openssh-clients \
        vim-enhanced \
        zip \
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
# available multiplexer.
RUN microdnf -y --enablerepo=epel install \
        bat \
        ccache \
        fzf \
        git-lfs \
        ncdu \
        ripgrep \
        screen \
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

# GitHub CLI, from GitHub's own el9 repo (x86_64 and aarch64)
RUN curl -fsSL https://cli.github.com/packages/rpm/gh-cli.repo -o /etc/yum.repos.d/gh-cli.repo && \
    microdnf install -y gh && \
    microdnf clean all && \
    rm -rf /var/cache/dnf

# Shell ergonomics. Loaded last so it wins over the env setup from the stages below.
RUN printf '%s\n' \
    'if [[ $- == *i* ]]; then' \
    '  [ -f /usr/share/bash-completion/bash_completion ] && . /usr/share/bash-completion/bash_completion' \
    '  [ -f /usr/share/git-core/contrib/completion/git-prompt.sh ] && . /usr/share/git-core/contrib/completion/git-prompt.sh' \
    '  export GIT_PS1_SHOWDIRTYSTATE=1' \
    '  PS1="\[\e[1;32m\]\u@${E3SM_ENV:-ghci}\[\e[0m\]:\[\e[1;34m\]\w\[\e[0;33m\]$(__git_ps1 " (%s)" 2>/dev/null)\[\e[0m\]\$ "' \
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

# The base image rewrites git@github.com: -> https:// so CI can fetch submodules
# anonymously. Here that would override an SSH remote and force an HTTPS credential prompt
# instead of using the ssh-agent a dev container forwards, so drop it.
RUN git config --system --unset-all url."https://github.com/".insteadOf

# Pre-create the dirs a dev container typically mounts volumes onto. A named volume
# mounted at a path that does NOT exist in the image is created root-owned, and then the
# non-root user cannot write to it.
RUN mkdir -p /home/${E3SM_USER}/.cache/ccache \
             /home/${E3SM_USER}/.config \
             /home/${E3SM_USER}/.claude \
             /home/${E3SM_USER}/.codex \
             /home/${E3SM_USER}/.copilot && \
    chown -R ${E3SM_USER}:${E3SM_USER} /home/${E3SM_USER}

# A bind-mounted repo is owned by the host's uid, which need not be ours; without this git
# refuses to operate on it ("dubious ownership"). Normal for a dev container.
RUN git config --system --add safe.directory '*'

# Where the per-user installers below put their binaries
RUN printf '%s\n' \
    'export PATH=$HOME/.local/bin:$HOME/.opencode/bin:$PATH' > /etc/profile.d/user-tools.sh

USER ${E3SM_USER}

# uv, and the coding agents. Each comes from its own upstream installer and lands in
# $HOME, so `uv self update` / `claude update` / `opencode upgrade` / `codex --upgrade`
# all work inside a running container without root. Deliberately unpinned: pinning would
# defeat the self-update these are installed for.
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
RUN curl -fsSL https://claude.ai/install.sh | bash
RUN curl -fsSL https://opencode.ai/install | bash
RUN curl -fsSL https://chatgpt.com/codex/install.sh | sh
RUN curl -fsSL https://gh.io/copilot-install | bash

WORKDIR /projects/e3sm/work

ENTRYPOINT []
CMD [ "/bin/bash", "--login" ]
