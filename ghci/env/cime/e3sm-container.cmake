# CIME build settings for the e3sm-container machine (config_machines.xml), any compiler.
# Kokkos is left without an arch: the image runs on any host of its arch, so Kokkos must not
# assume the build host's CPU.
string(APPEND KOKKOS_OPTIONS " -DKokkos_ENABLE_DEPRECATED_CODE_4=OFF")
