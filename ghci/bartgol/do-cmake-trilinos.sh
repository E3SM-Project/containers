SRC_DIR=${WORK_DIR}/trilinos/trilinos-src/develop
INSTALL_DIR=${WORK_DIR}/trilinos/trilinos-install/${HOST}/${COMPILER}/sacado/release

rm -rf CMakeFiles
rm -f  CMakeCache.txt

cmake -Wno-dev                                            \
  -D CMAKE_BUILD_TYPE:STRING=RELEASE                      \
  -D CMAKE_INSTALL_PREFIX:STRING=${INSTALL_DIR}           \
  -D CMAKE_VERBOSE_MAKEFILE:BOOL=OFF                      \
  -D CMAKE_CXX_COMPILER:STRING="g++"                      \
  -D BUILD_SHARED_LIBS:BOOL=ON                            \
  \
  -D Trilinos_VERBOSE_CONFIGURE:BOOL=OFF                  \
  -D Trilinos_ENABLE_EXAMPLES:BOOL=OFF                    \
  -D Trilinos_ENABLE_TESTS:BOOL=OFF                       \
  -D Trilinos_ENABLE_OpenMP:BOOL=OFF                      \
  -D Trilinos_ENABLE_ALL_PACKAGES:BOOL=OFF                \
  -D Trilinos_ENABLE_ALL_OPTIONAL_PACKAGES:BOOL=OFF       \
  \
  -D Trilinos_ENABLE_Sacado:BOOL=ON                       \
  \
  ${SRC_DIR}
