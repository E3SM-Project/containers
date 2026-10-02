#!/bin/bash
# Run as the image's default user, under a login shell, against a -dev image:
# docker run --rm -e EXPECT_CUDA=no -v "$PWD/ghci/tests:/opt/ghci-tests:ro" \
#   IMAGE bash -l /opt/ghci-tests/smoke-dev.sh
#
# The dev layer must not break the env underneath it, so this runs the env smoke test first,
# then checks what the dev layer adds: the tools on PATH, and the ownership a dev container
# relies on (volumes mounted onto pre-created dirs, a writable npm prefix and work dir).
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
step() { echo "== $*"; }

bash "$here/smoke.sh"

step "dev tools"
for tool in ninja gdb strace ccache rg fzf tig gh node npm uv vim ssh git-lfs; do
    command -v "$tool" > /dev/null || { echo "$tool is not on PATH" >&2; exit 1; }
done
node --version
gh --version | sed -n 1p

step "coding agents"
# --version only: no network, no login.
for agent in claude opencode codex copilot; do
    command -v "$agent" > /dev/null || { echo "$agent is not on PATH" >&2; exit 1; }
    echo "$agent $("$agent" --version 2>&1 | sed -n 1p)"
done

step "ownership"
user=$(id -un)
for dir in ~/.cache/ccache ~/.config ~/.claude ~/.codex ~/.copilot ~/.local/share/opencode \
           /projects/e3sm/work; do
    test "$(stat -c %U "$dir")" = "$user" || { echo "$dir is not owned by $user" >&2; exit 1; }
    test -w "$dir"
done
test -n "${NPM_CONFIG_PREFIX:-}"
mkdir -p "$NPM_CONFIG_PREFIX"
test -w "$NPM_CONFIG_PREFIX"

step "git"
# The env image's https rewrite would override SSH remotes in a dev container.
if git config --system --get-all url.https://github.com/.insteadof; then
    echo "the system git config still rewrites GitHub URLs to https" >&2
    exit 1
fi

step "non-login commands"
# e3sm-env gives a command the login environment without a login shell, starting from an
# environment with none of it (as docker exec or a batch launcher would).
env -i PATH=/usr/bin:/bin HOME="$HOME" /usr/local/bin/e3sm-env mpicc --version | sed -n 1p

echo "dev smoke test passed"
