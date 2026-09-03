SRC_DIR=/projects/e3sm/software/trilinos/source
INSTALL_DIR=/projects/e3sm/software/trilinos/install

PARMETIS_INCLUDE_DIRS="${PARMETIS_ROOT}/include;${METIS_ROOT}/include"
PARMETIS_LIBRARY_DIRS="${PARMETIS_ROOT}/lib;${METIS_ROOT}/lib"
NETCDF_INCLUDE_DIRS="${NETCDF_C_ROOT}/include;${PNETCDF_ROOT}/include"
NETCDF_LIBRARY_DIRS="${NETCDF_C_ROOT}/lib64;${PNETCDF_ROOT}/lib"

rm -rf CMakeFiles
rm -f  CMakeCache.txt

cmake -Wno-dev \
  \
  -D CMAKE_BUILD_TYPE:STRING=RELEASE                              \
  -D CMAKE_INSTALL_PREFIX:STRING=${INSTALL_DIR}                   \
  -D CMAKE_VERBOSE_MAKEFILE:BOOL=OFF                              \
  -D CMAKE_C_COMPILER:STRING="mpicc"                              \
  -D CMAKE_CXX_COMPILER:STRING="mpicxx"                           \
  -D CMAKE_Fortran_COMPILER:STRING="mpifort"                      \
  -D CMAKE_CXX_FLAGS:STRING="${MY_CXX_FLAGS}"                     \
  -D CMAKE_EXE_LINKER_FLAGS:STRING="-ldl"                         \
  -D BUILD_SHARED_LIBS:BOOL=ON                                    \
  \
  -D Trilinos_VERBOSE_CONFIGURE:BOOL=OFF                          \
  -D Trilinos_ENABLE_EXAMPLES:BOOL=OFF                            \
  -D Trilinos_ENABLE_TESTS:BOOL=OFF                               \
  -D Trilinos_ENABLE_EXPLICIT_INSTANTIATION:BOOL=ON               \
  -D Trilinos_ENABLE_OpenMP:BOOL=OFF                              \
  -D Trilinos_ENABLE_ALL_PACKAGES:BOOL=OFF                        \
  -D Trilinos_ENABLE_ALL_OPTIONAL_PACKAGES:BOOL=OFF               \
  \
  -D Trilinos_ENABLE_Amesos2:BOOL=ON                              \
  -D Trilinos_ENABLE_Anasazi:BOOL=ON                              \
  -D Trilinos_ENABLE_Belos:BOOL=ON                                \
  -D Trilinos_ENABLE_Ifpack2:BOOL=ON                              \
  -D Trilinos_ENABLE_Intrepid2:BOOL=ON                            \
  -D Trilinos_ENABLE_Kokkos:BOOL=ON                               \
  -D Trilinos_ENABLE_KokkosKernels:BOOL=ON                        \
  -D Trilinos_ENABLE_MueLu:BOOL=ON                                \
  -D Trilinos_ENABLE_NOX:BOOL=ON                                  \
  -D Trilinos_ENABLE_Pamgen:BOOL=ON                               \
  -D Trilinos_ENABLE_PanzerExprEval:BOOL=ON                       \
  -D Trilinos_ENABLE_PanzerDofMgr:BOOL=ON                         \
  -D Trilinos_ENABLE_Phalanx:BOOL=ON                              \
  -D Trilinos_ENABLE_Piro:BOOL=ON                                 \
  -D Trilinos_ENABLE_PyTrilinos:BOOL=OFF                          \
  -D Trilinos_ENABLE_ROL:BOOL=ON                                  \
  -D Trilinos_ENABLE_Sacado:BOOL=ON                               \
  -D Trilinos_ENABLE_SEACAS:BOOL=ON                               \
  -D Trilinos_ENABLE_SEACASExodus:BOOL=ON                         \
  -D Trilinos_ENABLE_SEACASIoss:BOOL=ON                           \
  -D Trilinos_ENABLE_Shards:BOOL=ON                               \
  -D Trilinos_ENABLE_ShyLU_DDFROSch:BOOL=ON                       \
  -D Trilinos_ENABLE_STKExprEval:BOOL=ON                          \
  -D Trilinos_ENABLE_STKIO:BOOL=ON                                \
  -D Trilinos_ENABLE_STKMesh:BOOL=ON                              \
  -D Trilinos_ENABLE_STKTopology:BOOL=ON                          \
  -D Trilinos_ENABLE_Stratimikos:BOOL=ON                          \
  -D Trilinos_ENABLE_Teko:BOOL=ON                                 \
  -D Trilinos_ENABLE_Tempus:BOOL=ON                               \
  -D Trilinos_ENABLE_Teuchos:BOOL=ON                              \
  -D Trilinos_ENABLE_Thyra:BOOL=ON                                \
  -D Trilinos_ENABLE_ThyraTpetraAdapters:BOOL=ON                  \
  -D Trilinos_ENABLE_Tpetra:BOOL=ON                               \
  -D Trilinos_ENABLE_Zoltan:BOOL=ON                               \
  -D Trilinos_ENABLE_Zoltan2:BOOL=ON                              \
  \
  -D Amesos2_ENABLE_KLU2:BOOL=ON                                  \
  -D Phalanx_ENABLE_TEUCHOS_TIME_MONITOR:BOOL=ON                  \
  -D Phalanx_ALLOW_MULTIPLE_EVALUATORS_FOR_SAME_FIELD:BOOL=OFF    \
  -D Kokkos_ENABLE_OPENMP:BOOL=OFF                                \
  -D Stratimikos_ENABLE_TEUCHOS_TIME_MONITOR:BOOL=ON              \
  -D STK_HIDE_DEPRECATED_CODE:BOOL=ON                             \
  -D Tpetra_INST_SERIAL:BOOL=ON                                   \
  -D Tpetra_ENABLE_TESTS:BOOL=OFF                                 \
  -D Zoltan_ENABLE_ULLONG_IDS:BOOL=ON                             \
  \
  -D TPL_ENABLE_gtest:BOOL=OFF                                    \
  -D TPL_ENABLE_MPI:BOOL=ON                                       \
  -D TPL_ENABLE_Boost:BOOL=ON                                     \
  -D TPL_ENABLE_HDF5:BOOL=ON                                      \
  -D TPL_ENABLE_HWLOC:BOOL=OFF                                    \
  -D TPL_ENABLE_Matio:BOOL=OFF                                    \
  -D TPL_ENABLE_Netcdf:BOOL=ON                                    \
  -D TPL_ENABLE_ParMETIS:BOOL=ON                                  \
  -D TPL_Netcdf_PARALLEL:BOOL=ON                                  \
  -D TPL_ENABLE_X11:BOOL=OFF                                      \
  \
  -D MPI_BASE_DIR:PATH=${MPI_ROOT}                                \
  -D BLAS_LIBRARY_DIRS:PATH=${BLAS_ROOT}/lib                      \
  -D LAPACK_LIBRARY_DIRS:PATH=${BLAS_ROOT}/lib                    \
  -D HDF5_INCLUDE_DIRS:PATH=${HDF5_ROOT}/include                  \
  -D HDF5_LIBRARY_DIRS:PATH=${HDF5_ROOT}/lib                      \
  -D Netcdf_INCLUDE_DIRS:STRING=${NETCDF_INCLUDE_DIRS}            \
  -D Netcdf_LIBRARY_DIRS:STRING=${NETCDF_LIBRARY_DIRS}            \
  -D ParMETIS_INCLUDE_DIRS:STRING=${PARMETIS_INCLUDE_DIRS}        \
  -D ParMETIS_LIBRARY_DIRS:STRING=${PARMETIS_LIBRARY_DIRS}        \
  -D Boost_INCLUDE_DIRS:PATH=${BOOST_ROOT}/include                \
  -D Boost_LIBRARY_DIRS:PATH=${BOOST_ROOT}/lib                    \
  \
  ${SRC_DIR}
