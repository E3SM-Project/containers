# OpenMP only for threaded builds, as in E3SM's universal.cmake: an unthreaded case that still
# enables it gets a Kokkos whose default space (OpenMP) does not match the build, which Omega
# (OMEGA_ARCH=SERIAL) checks for and fails on.
if (compile_threaded)
  string(APPEND KOKKOS_OPTIONS " -DKokkos_ENABLE_OPENMP=ON")
endif()

# Help find_package find the right BLAS (MKL)
set(BLA_VENDOR "Intel10_64lp" CACHE STRING "")
