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
# CASES picks what runs, any of: wcycl (the coupled MOAB case), aqp (the EAMxx case), eamxx
# (EAMxx's standalone tests); all three by default. CI runs one per job, side by side.
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
: "${CASES:=wcycl aqp eamxx}"
src=/projects/e3sm/work/E3SM
scratch="$HOME/e3sm_scratch"
step() { echo "== $*"; }

step "CIME machine"
# The env images ship the machine without enabling it (the -dev images enable it at login);
# opt in the way a user would.
# shellcheck source=/dev/null
. /projects/e3sm/cime/enable.sh
test "${CIME_MACHINE:-}" = e3sm-container || { echo "CIME_MACHINE is '${CIME_MACHINE:-}', not e3sm-container" >&2; exit 1; }
# The variant's default compiler: the first one the machine lists
compiler=$(sed -n 's:.*<COMPILERS>\([^,<]*\).*:\1:p' "$HOME/.cime/config_machines.xml")
echo "machine $CIME_MACHINE, compiler $compiler, build only: $BUILD_ONLY, cases: $CASES"
echo "E3SM $(git -C "$src" rev-parse HEAD 2>/dev/null || echo unknown)"
cd "$src/cime/scripts"
./query_config --machines "$CIME_MACHINE"

# CIME (and EAMxx's check-input) first probes the inputdata server with `wget --spider` on its
# root, and reports "Could not connect" if that takes over 60 s. With wget's defaults (15 min
# read timeout, 20 tries) one stalled connection uses up all 60 s; short timeouts and a few
# tries let wget recover from it in time. Only for wget run from this script.
WGETRC=$(mktemp)
export WGETRC
printf '%s\n' 'timeout = 10' 'tries = 4' 'waitretry = 2' 'retry_connrefused = on' > "$WGETRC"

# wcycl names no machine, so it relies on CIME_MACHINE; aqp names it explicitly, which a
# testmod requires.
tests=()
for c in $CASES; do
    case "$c" in
        wcycl) tests+=(SMS_Vmoab_P8_Ln5.ne4pg2_oQU480.WCYCL2010NS) ;;
        aqp) tests+=("SMS_P8_Ln5.ne4_ne4.F2000-SCREAMv1-AQP1.e3sm-container_${compiler}.eamxx-L72") ;;
        eamxx) ;;
        *) echo "unknown case '$c' in CASES (wcycl, aqp, eamxx)" >&2; exit 1 ;;
    esac
done
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

mkdir -p "$scratch"
if [ "${#tests[@]}" -gt 0 ]; then
    step "create_test ${tests[*]}"
    # --test-id keeps the case directories' names predictable for the logs CI uploads.
    # --proc-pool: create_test will not start a run with more ranks than its pool, which
    # defaults to the cores plus 25%. The machine oversubscribes, so let the 8-rank runs
    # start on a 4-core runner too (one at a time).
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
fi

if [[ " $CASES " != *" eamxx "* ]]; then
    :
elif [ "$BUILD_ONLY" = yes ]; then
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
        # CMake wraps the message, so match it with the line breaks folded into spaces
        log=$(tr -s ' \n' '  ' < "$scratch/eamxx-ctest.log")
        [[ $log == *"failed at config time"* && $log == *"Could not connect to repo"* ]] &&
            [ "$attempt" -lt 3 ] || exit "$rc"
        echo "inputdata server unreachable while configuring; retrying in $((attempt * 60)) s" >&2
        sleep $((attempt * 60))
    done
fi

echo "E3SM cases passed"
