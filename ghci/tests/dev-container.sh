#!/bin/bash
# Checks for the -dev images that need root to set up what a Dev Containers host does to the
# container: a checkout owned by another uid, and a remapped uid. Run as root, in a
# throwaway container -- it changes e3sm's uid:
# docker run --rm --user root -v "$PWD/ghci/tests:/opt/ghci-tests:ro" \
#   IMAGE-dev bash /opt/ghci-tests/dev-container.sh
#
# Meant for the -dev smoke job (#72), next to ghci/tests/smoke.sh.
set -euo pipefail

test "$(id -u)" -eq 0 || { echo "run this as root (docker run --user root ...)" >&2; exit 1; }
work=$(mktemp -d)
chmod 0755 "$work"
trap 'rm -rf "$work"' EXIT
step() { echo "== $*"; }
# A fresh login shell as e3sm, the way VS Code's terminals and userEnvProbe get one
as_e3sm() { sudo -u e3sm -H bash -lc "$1"; }

step "git: a checkout owned by another uid is trusted under /projects/e3sm/work only"
# Like a bind mount from a host whose uid is not e3sm's: a repo with a submodule, owned by
# uid 4321, in the workspace and somewhere else
g() { git -c user.name=smoke -c user.email=smoke@localhost -c protocol.file.allow=always "$@"; }
g init -q "$work/sub"
g -C "$work/sub" commit -q --allow-empty -m sub
g init -q "$work/E3SM"
g -C "$work/E3SM" submodule --quiet add "$work/sub" externals/sub
g -C "$work/E3SM" commit -q -m super
cp -a "$work/E3SM" /projects/e3sm/work/E3SM
cp -a "$work/E3SM" "$work/elsewhere"
chown -R 4321:4321 /projects/e3sm/work/E3SM "$work/elsewhere"
as_e3sm 'git -C /projects/e3sm/work/E3SM status --short'
as_e3sm 'git -C /projects/e3sm/work/E3SM submodule foreach --recursive git status --short'
as_e3sm 'cd ~/work/E3SM/externals/sub && git status --short'
out=$(as_e3sm "git -C '$work/elsewhere' status --short" 2>&1) || true
grep -q 'dubious ownership' <<<"$out" || { echo "git trusts a foreign-owned repo outside /projects/e3sm/work: $out" >&2; exit 1; }
rm -rf /projects/e3sm/work/E3SM

step "uid 1000, nothing remapped: e3sm-fix-ownership does nothing"
test "$(id -u e3sm)" -eq 1000
out=$(as_e3sm 'e3sm-fix-ownership 2>&1')
test -z "$out" || { echo "unexpected output: $out" >&2; exit 1; }

step "Dev Containers uid remap (updateRemoteUserUID) to 1234"
# What the extension's updateUID step does: new uid/gid, and only the home re-owned
groupmod -g 1234 e3sm
usermod -u 1234 -g 1234 e3sm
chown -R 1234:1234 /home/e3sm
# Without the fix, this is the bug: the venv still belongs to uid 1000
as_e3sm 'test ! -w "$VIRTUAL_ENV/lib"'

step "e3sm-fix-ownership, then pip install into the venv and write under /projects/e3sm"
as_e3sm e3sm-fix-ownership
mkdir "$work/pkg" "$work/pkg/demo"
echo 'X = 1' > "$work/pkg/demo/__init__.py"
cat > "$work/pkg/pyproject.toml" <<'TOML'
[project]
name = "demo"
version = "0.1"
[build-system]
requires = ["setuptools"]
build-backend = "setuptools.build_meta"
TOML
# pip builds in the source tree, so it has to be e3sm's
chown -R e3sm:e3sm "$work/pkg"
as_e3sm "cd /tmp && pip install --no-index --no-build-isolation --no-cache-dir '$work/pkg' >/dev/null && python3 -c 'import demo'"
as_e3sm 'touch /projects/e3sm/work/probe /projects/e3sm/data/probe /projects/e3sm/software/probe'
# Done: a second run (the next container start, for instance) has nothing to do
out=$(as_e3sm 'e3sm-fix-ownership 2>&1')
test -z "$out" || { echo "unexpected output on the second run: $out" >&2; exit 1; }

echo "dev container checks passed"
