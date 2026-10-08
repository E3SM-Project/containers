#!/bin/bash
# Build and run a few small E3SM cases in the image, with the image's own CIME machine
# (e3sm-container, opted into below) and nothing else: no --machine, no hostname trick. The
# smoke tests prove the toolchain; this proves E3SM builds and runs on it. Run as the image's
# default user, under a login shell, with an E3SM checkout (submodules included) at
# /projects/e3sm/work/E3SM:
# docker run --rm -e BUILD_ONLY=no \
#   -v /path/to/E3SM:/projects/e3sm/work/E3SM \
#   -v /path/to/inputdata:/projects/e3sm/data/inputdata \
#   -v /path/to/scratch:/home/e3sm/e3sm_scratch \
#   -v "$PWD/ghci/tests:/opt/ghci-tests:ro" \
#   IMAGE bash -l /opt/ghci-tests/e3sm-case.sh
#
# Missing inputdata is downloaded into the inputdata mount. BUILD_ONLY=yes (the CUDA images:
# CI has no GPU) builds the cases without running them, and skips the EAMxx standalone tests.
# The checkout and both mounts must be writable by the e3sm user (uid 1000).
#
# The case list is #93's, with WCYCL2010NS in place of F1850: F1850's emissions alone are
# ~20 GB of inputdata, while the coupled 2010 case needs ~7 GB in all (no more than F2010,
# whose big atmosphere files it shares), fits the runners and the Actions cache, and puts
# every active component through the MOAB coupler.
# Results end up in ~/e3sm_scratch/<test>.<id>/TestStatus and ~/e3sm_scratch/eamxx-ctest.
set -euo pipefail

: "${BUILD_ONLY:=no}"
src=/projects/e3sm/work/E3SM
scratch="$HOME/e3sm_scratch"
step() { echo "== $*"; }

step "CIME machine"
# The env images ship the machine without enabling it (the -dev images enable it at login);
# opt in the way a user would.
# shellcheck source=/dev/null
. /opt/share/e3sm-cime-machine.sh
test "${CIME_MACHINE:-}" = e3sm-container || { echo "CIME_MACHINE is '${CIME_MACHINE:-}', not e3sm-container" >&2; exit 1; }
# The variant's default compiler: the first one the machine lists
compiler=$(sed -n 's:.*<COMPILERS>\([^,<]*\).*:\1:p' "$HOME/.cime/config_machines.xml")
echo "machine $CIME_MACHINE, compiler $compiler, build only: $BUILD_ONLY"
cd "$src/cime/scripts"
./query_config --machines "$CIME_MACHINE"

# The first test names no machine, so it relies on CIME_MACHINE; the other names it
# explicitly, which a testmod requires.
tests=(
    SMS_Vmoab_P8_Ln5.ne4pg2_oQU480.WCYCL2010NS
    "SMS_P8_Ln5.ne4_ne4.F2000-SCREAMv1-AQP1.e3sm-container_${compiler}.eamxx-L72"
)
run_opt=()
[ "$BUILD_ONLY" = yes ] && run_opt=(--no-run)

# Files E3SM opens without asking for them, so nothing downloads them and the test dies on a
# missing file (#31): EAM's P3 builds the lookup table's path in micro_p3.F90, and EAMxx's
# spa standalone test fetches the ne4 SPA file while its input.yaml reads the ne2 one.
step "inputdata E3SM does not ask for"
inputdata=/projects/e3sm/data/inputdata
for f in atm/cam/physprops/p3_lookup_table_1.dat-v4.1.2 \
         atm/scream/init/spa_file_unified_and_complete_ne2np4L72_20231222.nc; do
    [ -f "$inputdata/$f" ] && continue
    mkdir -p "$(dirname "$inputdata/$f")"
    curl -fsSL -o "$inputdata/$f.part" "https://web.lcrc.anl.gov/public/e3sm/inputdata/$f"
    mv "$inputdata/$f.part" "$inputdata/$f"
    echo "fetched $f"
done

step "create_test ${tests[*]}"
mkdir -p "$scratch"
# --test-id keeps the case directories' names predictable for the logs CI uploads.
# --proc-pool: create_test will not start a run with more ranks than its pool, which defaults
# to the cores plus 25%. The machine oversubscribes, so let the 8-rank runs start on a
# 4-core runner too (one at a time).
cores=$(nproc)
rc=0
./create_test "${tests[@]}" "${run_opt[@]}" --wait --test-id e3sm-case \
    --parallel-jobs "$cores" --proc-pool "$(( cores > 8 ? cores : 8 ))" || rc=$?
# No case directory at all if create_test failed early: then there is nothing to show
shopt -s nullglob
for status in "$scratch"/*.e3sm-case/TestStatus; do
    echo "-- $status"
    cat "$status"
done
shopt -u nullglob
[ "$rc" -eq 0 ] || { echo "create_test failed ($rc)" >&2; exit "$rc"; }

if [ "$BUILD_ONLY" = yes ]; then
    step "EAMxx standalone tests skipped (build only)"
else
    # The build type E3SM's own CI uses for this compiler: single precision with gnu, opt
    # (double) with intel, where the single-precision build is untested upstream and does
    # not compile (ambiguous float/double calls that icpx rejects).
    eamxx_test=sp
    [ "$compiler" = intel ] && eamxx_test=opt
    step "test-all-eamxx -m e3sm-container -t $eamxx_test"
    # No baselines: -b is left out, which skips every baseline comparison. The output is
    # also kept in eamxx-ctest.log, for CI to upload with ctest's own logs.
    # EAMxx downloads its test inputs while configuring, and the inputdata server sometimes
    # refuses a connection ("Could not connect to repo"). Such a configure failure is retried:
    # what was already downloaded stays, so each attempt needs less. Anything else fails.
    for attempt in 1 2 3; do
        rc=0
        "$src/components/eamxx/scripts/test-all-eamxx" -m e3sm-container -t "$eamxx_test" \
            -w "$scratch/eamxx-ctest" 2>&1 | tee "$scratch/eamxx-ctest.log" || rc=$?
        [ "$rc" -eq 0 ] && break
        grep -q 'failed at config time' "$scratch/eamxx-ctest.log" &&
            grep -q 'Could not connect to repo' "$scratch/eamxx-ctest.log" &&
            [ "$attempt" -lt 3 ] || exit "$rc"
        echo "inputdata server unreachable while configuring; retrying in $((attempt * 60)) s" >&2
        sleep $((attempt * 60))
    done
fi

echo "E3SM cases passed"
