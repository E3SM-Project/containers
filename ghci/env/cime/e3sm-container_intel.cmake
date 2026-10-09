string(APPEND KOKKOS_OPTIONS " -DKokkos_ENABLE_OPENMP=ON")

# Help find_package find the right BLAS (MKL)
set(BLA_VENDOR "Intel10_64lp" CACHE STRING "")
