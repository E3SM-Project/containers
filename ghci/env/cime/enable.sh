# Opt in to this image's CIME machine, e3sm-container (the files next to this script):
#   . /projects/e3sm/cime/enable.sh
# The -dev images source it at login; the env images only ship it, so nothing changes for
# CI or downstream images unless they ask.
#
# - Copies the machine files into ~/.cime, unless ~/.cime already has a config_machines.xml
#   (yours wins; add the e3sm-container entry to it by hand if you want both).
# - Exports CIME_MACHINE=e3sm-container if ~/.cime has the machine and CIME_MACHINE is not set
#   already, so create_newcase/create_test need no --machine. An explicit machine (in a test
#   name, --machine) still wins over it.
#
# Sourced from login shells, so it must never fail or print.
if [ -n "${HOME:-}" ] && [ -w "$HOME" ] && [ ! -e "$HOME/.cime/config_machines.xml" ]; then
    mkdir -p "$HOME/.cime" 2> /dev/null &&
        cp -n /projects/e3sm/cime/config_machines.xml /projects/e3sm/cime/*.cmake \
            /projects/e3sm/cime/scream_mach_specs.py "$HOME/.cime/" 2> /dev/null
fi
if [ -z "${CIME_MACHINE:-}" ] && grep -qs 'MACH="e3sm-container"' "$HOME/.cime/config_machines.xml"; then
    export CIME_MACHINE=e3sm-container
fi
true
