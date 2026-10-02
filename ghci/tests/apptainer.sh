#!/bin/bash
# Qualify an env image under Apptainer, the way HPC users run it. Needs apptainer and no
# special privileges. Usage:
#   ghci/tests/apptainer.sh SOURCE
# where SOURCE is anything `apptainer build` accepts: docker://ghcr.io/e3sm-project/e3sm-ghci:gnu-cpu-env,
# docker-daemon:IMAGE, or an existing .sif file. Set EXPECT_CUDA=yes|no to match the image.
#
# What differs from `docker run`, and is checked here: the user is the host user (not e3sm),
# the image is read-only, sudo does not work, there is no login shell unless one is asked for,
# and the host environment leaks in unless --cleanenv is given. Then the regular smoke checks
# run inside the container (ghci/tests/smoke.sh, with SMOKE_READONLY=yes).
# Not covered: GPUs (--nv) and multi-node MPI, which need real hardware.
set -euo pipefail

source=${1:?usage: apptainer.sh SOURCE}
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
step() { echo "== $*"; }
fail() { echo "FAIL: $*" >&2; exit 1; }

case "$source" in
    *.sif) image=$source ;;
    *)
        step "build the SIF from $source"
        image=$work/image.sif
        APPTAINER_TMPDIR=$work apptainer build "$image" "$source"
        ;;
esac
run() { apptainer exec --cleanenv "$image" "$@"; }

step "runs as the host user, not e3sm"
uid=$(run id -u)
test "$uid" = "$(id -u)" || fail "uid in the container is $uid, expected $(id -u)"
test "$uid" -ne 0 || fail "running as root"

step "image environment survives --cleanenv"
test "$(run printenv E3SM_USER)" = e3sm
test "$(run printenv COMPILER)" = "$(run bash -lc 'echo "$COMPILER"')"

step "login activation: bash -l, e3sm-env and the runscript (ENTRYPOINT e3sm-env, CMD bash --login)"
test -n "$(run bash -lc 'echo "$SPACK_ARCH"')" || fail "bash -l did not source /etc/profile.d"
run e3sm-env mpicc --version >/dev/null
# shellcheck disable=SC2016  # the login shell inside the container expands these
out=$(echo 'echo "arch=$SPACK_ARCH"; command -v mpirun' | apptainer run --cleanenv "$image")
grep -q '^arch=linux-rhel9-' <<<"$out" || fail "apptainer run did not give a login shell: $out"

step "apptainer run IMAGE CMD: the command runs through the ENTRYPOINT (e3sm-env)"
apptainer run --cleanenv "$image" cmake --version >/dev/null || fail "apptainer run cmake: no login environment"
out=$(apptainer run --cleanenv "$image" python3 -c 'import sys; print(sys.prefix)')
test "$out" = /projects/e3sm/software/eamxx-venv || fail "apptainer run python3 is $out, not the venv"
out=$(apptainer run --cleanenv "$image" printf '%s\n' 'a b' c)
test "$out" = $'a b\nc' || fail "apptainer run did not preserve the arguments: $out"

step "read-only image: writes fail, --writable-tmpfs and --overlay make them work"
if run bash -c 'touch /projects/e3sm/data/probe' 2>/dev/null; then
    fail "image is unexpectedly writable"
fi
apptainer exec --cleanenv --writable-tmpfs "$image" bash -c 'touch /projects/e3sm/data/probe'
apptainer overlay create --size 64 "$work/overlay.img" >/dev/null
apptainer exec --cleanenv --overlay "$work/overlay.img" "$image" bash -c 'echo kept > /projects/e3sm/data/probe'
test "$(apptainer exec --cleanenv --overlay "$work/overlay.img" "$image" cat /projects/e3sm/data/probe)" = kept

step "python: pip install works with --writable-tmpfs; the venv itself is read-only"
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
apptainer exec --cleanenv --bind "$work/pkg:/mnt/pkg" --writable-tmpfs "$image" bash -lc \
    'pip install --no-index --no-build-isolation --no-cache-dir /mnt/pkg >/dev/null && python -c "import demo"'
if run bash -lc 'touch "$VIRTUAL_ENV/probe"' 2>/dev/null; then
    fail "venv is unexpectedly writable"
fi

step "data binds onto /projects/e3sm/data/inputdata"
mkdir "$work/inputdata"
echo data > "$work/inputdata/file"
test "$(apptainer exec --cleanenv --bind "$work/inputdata:/projects/e3sm/data/inputdata:ro" "$image" \
    cat /projects/e3sm/data/inputdata/file)" = data

step "smoke checks inside the container"
apptainer exec --cleanenv \
    --env SMOKE_READONLY=yes --env EXPECT_CUDA="${EXPECT_CUDA:-}" \
    --bind "$here:/mnt/ghci-tests:ro" \
    "$image" bash -l /mnt/ghci-tests/smoke.sh

echo "apptainer checks passed"
