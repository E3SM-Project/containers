# The GPU is not known when the image is built (CI has none), so the Kokkos arch defaults to
# Hopper, what E3SM's GPU CI runs on, and E3SM_KOKKOS_CUDA_ARCH overrides it, e.g.
# AMPERE80 or BLACKWELL100 (any Kokkos_ARCH_<name>).
if (DEFINED ENV{E3SM_KOKKOS_CUDA_ARCH})
  set(_e3sm_cuda_arch "$ENV{E3SM_KOKKOS_CUDA_ARCH}")
else()
  set(_e3sm_cuda_arch "HOPPER90")
endif()
string(APPEND KOKKOS_OPTIONS " -DKokkos_ENABLE_CUDA=ON -DKokkos_ARCH_${_e3sm_cuda_arch}=ON -DKokkos_ENABLE_CUDA_LAMBDA=ON")

# The image's MPI is not CUDA-aware
set(SCREAM_MPI_ON_DEVICE OFF CACHE STRING "")
