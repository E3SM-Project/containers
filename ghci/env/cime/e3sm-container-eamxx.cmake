# EAMxx standalone cmake settings for this image (see scream_mach_specs.py). Self-contained:
# this file is not in eamxx's machine-files directory, so it cannot include the files there.
# What the image is comes from /etc/e3sm/image.env.
file(STRINGS /etc/e3sm/image.env _e3sm_image_env)

set(SCREAM_MACHINE e3sm-container CACHE STRING "")
set(SCREAM_INPUT_ROOT /projects/e3sm/data/inputdata CACHE PATH "Path to SCREAM input data" FORCE)
set(Python_EXECUTABLE "/projects/e3sm/software/eamxx-venv/bin/python3" CACHE STRING "")
option(EAMXX_ENABLE_PYTHON "Whether to enable python interface from eamxx" ON)

option(Kokkos_ENABLE_DEPRECATED_CODE_4 "" OFF)

# No batch system: the test launcher spreads tests over the cores (or GPUs) itself
option(EKAT_TEST_LAUNCHER_MANAGE_RESOURCES "" ON)
set(EKAT_MPIRUN_EXE "mpirun" CACHE STRING "")
set(EKAT_MPI_NP_FLAG "-n" CACHE STRING "")
if (_e3sm_image_env MATCHES "E3SM_MPI=openmpi")
  # Open MPI refuses more ranks than the cores it was given; MPICH does not care
  set(EKAT_MPI_EXTRA_ARGS "--oversubscribe" CACHE STRING "")
endif()

if (_e3sm_image_env MATCHES "E3SM_COMPILER=intel")
  option(HOMME_USE_MKL "Whether to use Intel's MKL/oneMKL instead of blas/lapack" ON)
else()
  set(CMAKE_Fortran_FLAGS "-fallow-argument-mismatch" CACHE STRING "Fortran compiler flags" FORCE)
  set(BLAS_LIBRARIES "$ENV{BLAS_ROOT}/lib/libopenblas.so" CACHE STRING "Path to BLAS library" FORCE)
  set(LAPACK_LIBRARIES "$ENV{BLAS_ROOT}/lib/libopenblas.so" CACHE STRING "Path to LAPACK library" FORCE)
endif()

if (_e3sm_image_env MATCHES "E3SM_WITH_CUDA=yes")
  # See e3sm-container_gnugpu.cmake for the arch default
  if (DEFINED ENV{E3SM_KOKKOS_CUDA_ARCH})
    set(_e3sm_cuda_arch "$ENV{E3SM_KOKKOS_CUDA_ARCH}")
  else()
    set(_e3sm_cuda_arch "HOPPER90")
  endif()
  set(Kokkos_ENABLE_CUDA TRUE CACHE BOOL "")
  set(Kokkos_ENABLE_CUDA_LAMBDA TRUE CACHE BOOL "")
  set(Kokkos_ARCH_${_e3sm_cuda_arch} TRUE CACHE BOOL "")
  option(SCREAM_MPI_ON_DEVICE "Whether to use device pointers for MPI calls" OFF)
  set(SCREAM_TEST_MAX_RANKS 2 CACHE STRING "Upper limit on ranks for mpi tests")
else()
  set(Kokkos_ENABLE_OPENMP TRUE CACHE BOOL "")
  # Keep the threaded tests small enough for a laptop or a 4-core CI runner
  set(SCREAM_TEST_MAX_RANKS 4 CACHE STRING "Upper limit on number of ranks for mpi tests")
  set(SCREAM_TEST_MAX_THREADS 4 CACHE STRING "Upper limit on number of threads for threaded tests")
endif()
