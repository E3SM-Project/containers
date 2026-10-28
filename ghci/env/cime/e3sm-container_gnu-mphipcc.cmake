# GNU Fortran and C, with hipcc for C++ (the "mphipcc" of E3SM's craygnu-mphipcc on Frontier:
# mpicxx is told to compile with hipcc, see MPICH_CXX in config_machines.xml), for AMD GPUs.
# E3SM has no generic gnu-mphipcc.cmake, so this starts from its gnu.cmake. That is included
# from E3SM's source tree: CIME copies only the macro files a case names into the case, and
# follows the includes of the ones it copies from E3SM, not of the ones from ~/.cime like this.
include(${SRCROOT}/cime_config/machines/cmake_macros/gnu.cmake)

# The GPU is not known when the image is built (CI has none), so the Kokkos arch defaults to
# MI200 (gfx90a), and E3SM_KOKKOS_HIP_ARCH overrides it, e.g. AMD_GFX942 (any Kokkos_ARCH_AMD_GFX*
# name; the hipcc target, gfx942, follows from it).
if (DEFINED ENV{E3SM_KOKKOS_HIP_ARCH})
  set(_e3sm_hip_arch "$ENV{E3SM_KOKKOS_HIP_ARCH}")
else()
  set(_e3sm_hip_arch "AMD_GFX90A")
endif()
string(REGEX REPLACE "^AMD_" "" _e3sm_hip_target "${_e3sm_hip_arch}")
string(TOLOWER "${_e3sm_hip_target}" _e3sm_hip_target)

set(MPICXX "mpicxx") # Needs MPICH_CXX to use hipcc
set(SCXX "hipcc")

# Kokkos builds with hipcc, which uses gcc-toolset's libstdc++ and libgomp: no libomp mixed in
if (compile_threaded)
  string(APPEND CMAKE_CXX_FLAGS " -fopenmp=libgomp")
endif()

string(APPEND KOKKOS_OPTIONS " -DKokkos_ENABLE_HIP=ON")
string(APPEND KOKKOS_OPTIONS " -DKokkos_ARCH_${_e3sm_hip_arch}=ON")
string(APPEND KOKKOS_OPTIONS " -DKokkos_ENABLE_OPENMP=OFF")
string(APPEND KOKKOS_OPTIONS " -DAMDGPU_TARGETS=${_e3sm_hip_target} -DGPU_TARGETS=${_e3sm_hip_target}")
set(USE_HIP "TRUE")
set(AMDGPU_TARGETS "${_e3sm_hip_target}" CACHE STRING "")
set(GPU_TARGETS "${_e3sm_hip_target}" CACHE STRING "")
# CMake's native HIP language (components/CMakeLists.txt enables it) cannot detect an arch without a GPU
set(CMAKE_HIP_ARCHITECTURES "${_e3sm_hip_target}" CACHE STRING "")
string(APPEND CMAKE_HIP_FLAGS " $ENV{CXXFLAGS} -munsafe-fp-atomics")

# As on Frontier: the Fortran compiler links, so the HIP runtime and libstdc++ are added by hand
set(E3SM_LINK_WITH_FORTRAN "TRUE")
string(APPEND CMAKE_EXE_LINKER_FLAGS " -L$ENV{ROCM_PATH}/lib -lamdhip64 -lstdc++")

# The image's MPI is not GPU-aware
set(SCREAM_MPI_ON_DEVICE OFF CACHE STRING "")
