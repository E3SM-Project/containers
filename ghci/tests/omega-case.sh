#!/bin/bash
# Build Omega standalone and run its CTests in the image, with the image's own CIME machine
# (e3sm-container, opted into below) and its Metis/ParMETIS. The smoke tests prove the
# toolchain; this proves Omega builds and passes its unit tests on it. Run as the image's
# default user, under a login shell, with an Omega checkout at /projects/e3sm/work/Omega
# (the submodules a standalone build needs: externals/YAKL, externals/ekat,
# externals/scorpio, components/omega/external and cime):
# docker run --rm -e OMEGA_BUILD_TYPE=Release \
#   -v /path/to/Omega:/projects/e3sm/work/Omega \
#   -v /path/to/meshes:/projects/e3sm/data/omega-meshes \
#   -v /path/to/scratch:/home/e3sm/e3sm_scratch \
#   -v "$PWD/ghci/tests:/opt/ghci-tests:ro" \
#   IMAGE bash -l /opt/ghci-tests/omega-case.sh
#
# OMEGA_BUILD_TYPE is Release (the default) or Debug. Missing meshes are downloaded into the
# meshes mount. The checkout and both mounts must be writable by the e3sm user (uid 1000).
# Adapted from E3SM-Project/Omega#607's CI scripts.
# The build and ctest's logs end up in ~/e3sm_scratch/omega-build.
set -euo pipefail

: "${OMEGA_BUILD_TYPE:=Release}"
: "${CTEST_ARGS:=--timeout 900}"
src=/projects/e3sm/work/Omega
meshes=/projects/e3sm/data/omega-meshes
build="$HOME/e3sm_scratch/omega-build"
step() { echo "== $*"; }

step "CIME machine"
# The env images ship the machine without enabling it (the -dev images enable it at login);
# opt in the way a user would.
# shellcheck source=/dev/null
. /projects/e3sm/cime/enable.sh
test "${CIME_MACHINE:-}" = e3sm-container || { echo "CIME_MACHINE is '${CIME_MACHINE:-}', not e3sm-container" >&2; exit 1; }
# The variant's default compiler: the first one the machine lists
compiler=$(sed -n 's:.*<COMPILERS>\([^,<]*\).*:\1:p' "$HOME/.cime/config_machines.xml")
: "${METIS_ROOT:?METIS_ROOT is not set; was the image built with WITH_PARMETIS=yes?}"
: "${PARMETIS_ROOT:?PARMETIS_ROOT is not set; was the image built with WITH_PARMETIS=yes?}"
echo "machine $CIME_MACHINE, compiler $compiler, build type $OMEGA_BUILD_TYPE"
echo "Omega $(git -C "$src" rev-parse HEAD 2>/dev/null || echo unknown)"

# The meshes Omega's CTests read, as listed in its Quick Start guide
# (components/omega/doc/devGuide/QuickStart.md, "Getting test meshes")
step "meshes"
base=https://web.lcrc.anl.gov/public/e3sm/polaris/ocean/omega_ctest
mkdir -p "$meshes"
for entry in "OmegaMesh.nc ocean.QU.240km.omega_vars.260807.nc" \
             "OmegaSphereMesh.nc cosine_bell_icos480.omega_vars.260911.nc" \
             "OmegaPlanarMesh.nc PlanarPeriodic48x48.omega_vars.260825.nc"; do
    read -r name file <<< "$entry"
    [ -f "$meshes/$name" ] && continue
    # Into a .part file first, so an interrupted download never looks complete
    curl -fsSL --retry 4 --retry-delay 5 -o "$meshes/$name.part" "$base/$file"
    mv "$meshes/$name.part" "$meshes/$name"
    echo "fetched $name"
done

step "configure"
# Start from scratch, as Omega's dev guide recommends
rm -rf "$build"
mkdir -p "$build"
cmake \
    -DOMEGA_BUILD_TYPE="$OMEGA_BUILD_TYPE" \
    -DOMEGA_CIME_COMPILER="$compiler" \
    -DOMEGA_CIME_MACHINE="$CIME_MACHINE" \
    -DOMEGA_METIS_ROOT="$METIS_ROOT" \
    -DOMEGA_PARMETIS_ROOT="$PARMETIS_ROOT" \
    -DOMEGA_BUILD_TEST=ON \
    -Wno-dev \
    -S "$src/components/omega" \
    -B "$build"
cd "$build"
# OmegaBuild.cmake ignores create_newcase/case.setup failures; this is where they show
test -x omega_build.sh || { echo "CMake did not write omega_build.sh" >&2; exit 1; }

step "build"
./omega_build.sh

step "ctest $CTEST_ARGS"
for mesh in OmegaMesh.nc OmegaSphereMesh.nc OmegaPlanarMesh.nc; do
    ln -sf "$meshes/$mesh" "test/$mesh"
done
# shellcheck disable=SC2086  # CTEST_ARGS is a flag list
./omega_ctest.sh $CTEST_ARGS 2>&1 | tee "$build/omega-ctest.log"

echo "Omega CTests passed"
