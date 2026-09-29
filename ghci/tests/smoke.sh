#!/bin/bash
# Run as the image's default user, under a login shell:
# docker run --rm -e EXPECT_CUDA=no -v "$PWD/ghci/tests:/opt/ghci-tests:ro" \
#   IMAGE bash -l /opt/ghci-tests/smoke.sh
#
# Checks what E3SM itself needs from the image, not just that the tools exist: the login
# environment and module *_ROOT variables, the MPI wrappers' compiler, Fortran module files
# (.mod) that match that compiler, parallel I/O through netCDF-4/HDF5 and PnetCDF, LAPACK,
# and CMake finding the C++ dependencies the way E3SM's build does.
set -euo pipefail
# NOTE: no `| grep -q` or `| head` below: they exit early, the writer gets SIGPIPE, and
# pipefail turns that into a failure (exit 141) whenever the writer is still writing.

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cd "$work"
step() { echo "== $*"; }

step "image"
# shellcheck source=/dev/null
source /etc/e3sm/image.env
cat /etc/e3sm/image.env

step "login environment"
test "$(id -u)" -ne 0
test -n "$SPACK_ARCH"
test -n "$COMPILER_SPEC"
test "$VIRTUAL_ENV" = /projects/e3sm/software/eamxx-venv
test -w "$VIRTUAL_ENV/lib"
# A fresh login shell must come up clean: a module that fails to load only prints a warning.
login_errors=$(bash -lc true 2>&1 | grep -iE 'error|unable to locate|not found' || true)
if [ -n "$login_errors" ]; then
    echo "login shell reported errors:" >&2
    echo "$login_errors" >&2
    exit 1
fi
sudo -n true

step "module paths"
roots=(HDF5_ROOT NETCDF_C_ROOT NETCDF_FORTRAN_ROOT PARALLEL_NETCDF_ROOT MPI_ROOT YAML_CPP_ROOT BOOST_ROOT)
case "$E3SM_LAPACK" in
    intel-oneapi-mkl*) roots+=(MKLROOT) ;;
    *) roots+=(BLAS_ROOT LAPACK_ROOT) ;;
esac
for var in "${roots[@]}"; do
    test -d "${!var:-/nonexistent}" || { echo "$var is not set to a directory" >&2; exit 1; }
    echo "$var=${!var}"
done

step "tools"
cmake --version | sed -n 1p
mpirun --version | sed -n 1p
nc-config --version
nf-config --version
pnetcdf-config --version

step "MPI wrappers use ${COMPILER_SPEC}"
for wrapper in mpicc mpicxx mpifort; do
    "$wrapper" --version | sed -n 1p
    "$wrapper" --version | grep -F "${COMPILER_VERSION}" >/dev/null
done

step "python"
python3 "$here/check_python.py"
python3 - <<'PY'
import os
from pathlib import Path
import tempfile

import netCDF4
import numpy as np
from mpi4py import MPI
import torch
import xarray

with tempfile.TemporaryDirectory(dir=os.environ["VIRTUAL_ENV"]) as directory:
    path = Path(directory) / "test.nc"
    with netCDF4.Dataset(path, "w") as dataset:
        dataset.createDimension("x", 3)
        dataset.createVariable("x", "f8", ("x",))[:] = np.arange(3)
    with xarray.open_dataset(path) as dataset:
        np.testing.assert_array_equal(dataset.x.values, np.arange(3))
assert torch.arange(3).sum().item() == 3
if os.environ.get("EXPECT_CUDA") == "no":
    assert torch.version.cuda is None, "CPU image unexpectedly contains CUDA-enabled Torch"
elif os.environ.get("EXPECT_CUDA") == "yes":
    assert torch.version.cuda is not None, "CUDA image contains CPU-only Torch"
    import cupy  # noqa: F401  (importing needs no GPU)
print("MPI:", MPI.Get_library_version().splitlines()[0])
print("Torch:", torch.__version__, "CUDA build:", torch.version.cuda)
PY

step "MPI: C and Fortran (use mpi, use mpi_f08), 2 ranks"
cat > hello.c <<'C'
#include <mpi.h>
int main(int argc, char **argv) {
    int count;
    MPI_Init(&argc, &argv);
    MPI_Comm_size(MPI_COMM_WORLD, &count);
    MPI_Finalize();
    return count == 2 ? 0 : 1;
}
C
mpicc hello.c -o hello-c
mpirun -n 2 ./hello-c
cat > mpi_f.f90 <<'F90'
program mpi_f
    use mpi
    implicit none
    integer :: ierr, rank, total
    call MPI_Init(ierr)
    call MPI_Comm_rank(MPI_COMM_WORLD, rank, ierr)
    call MPI_Allreduce(rank + 1, total, 1, MPI_INTEGER, MPI_SUM, MPI_COMM_WORLD, ierr)
    if (total /= 3) error stop "allreduce gave the wrong answer"
    call MPI_Finalize(ierr)
end program mpi_f
F90
mpifort mpi_f.f90 -o mpi-f
mpirun -n 2 ./mpi-f
cat > mpi_f08.f90 <<'F90'
program mpi_f08_test
    use mpi_f08
    implicit none
    integer :: rank, total
    call MPI_Init()
    call MPI_Comm_rank(MPI_COMM_WORLD, rank)
    call MPI_Allreduce(rank + 1, total, 1, MPI_INTEGER, MPI_SUM, MPI_COMM_WORLD)
    if (total /= 3) error stop "allreduce gave the wrong answer"
    call MPI_Finalize()
end program mpi_f08_test
F90
mpifort mpi_f08.f90 -o mpi-f08
mpirun -n 2 ./mpi-f08

step "netCDF-Fortran: write and read back through the .mod files"
cat > nf.f90 <<'F90'
program nf
    use netcdf
    implicit none
    integer :: ncid, dimid, varid, values(3)
    call check(nf90_create("nf.nc", NF90_NETCDF4, ncid))
    call check(nf90_def_dim(ncid, "x", 3, dimid))
    call check(nf90_def_var(ncid, "v", NF90_INT, [dimid], varid))
    call check(nf90_enddef(ncid))
    call check(nf90_put_var(ncid, varid, [1, 2, 3]))
    call check(nf90_close(ncid))
    call check(nf90_open("nf.nc", NF90_NOWRITE, ncid))
    call check(nf90_get_var(ncid, varid, values))
    call check(nf90_close(ncid))
    if (any(values /= [1, 2, 3])) error stop "read back the wrong values"
contains
    subroutine check(status)
        integer, intent(in) :: status
        if (status /= nf90_noerr) then
            print *, trim(nf90_strerror(status))
            error stop 1
        end if
    end subroutine check
end program nf
F90
# netcdf-c lives in its own prefix, which nf-config --flibs does not add a -L for.
# shellcheck disable=SC2046
mpifort nf.f90 -o nf $(nf-config --fflags) $(nf-config --flibs) $(nc-config --libs)
./nf

step "parallel netCDF-4 (HDF5) and PnetCDF, 2 ranks"
cat > par.c <<'C'
#include <mpi.h>
#include <netcdf.h>
#include <netcdf_par.h>
#include <pnetcdf.h>
#include <stdio.h>
#define CHECK(call, what) do { int e = (call); if (e) { printf("%s: %d\n", what, e); MPI_Abort(MPI_COMM_WORLD, 1); } } while (0)
int main(int argc, char **argv) {
    int rank, ncid, dimid, varid, value;
    MPI_Offset start, count = 1;
    size_t nstart, ncount = 1;
    MPI_Init(&argc, &argv);
    MPI_Comm_rank(MPI_COMM_WORLD, &rank);
    value = rank; start = rank; nstart = rank;

    CHECK(nc_create_par("hdf5.nc", NC_NETCDF4 | NC_CLOBBER, MPI_COMM_WORLD, MPI_INFO_NULL, &ncid), "nc_create_par");
    CHECK(nc_def_dim(ncid, "x", 2, &dimid), "nc_def_dim");
    CHECK(nc_def_var(ncid, "v", NC_INT, 1, &dimid, &varid), "nc_def_var");
    CHECK(nc_enddef(ncid), "nc_enddef");
    CHECK(nc_var_par_access(ncid, varid, NC_COLLECTIVE), "nc_var_par_access");
    CHECK(nc_put_vara_int(ncid, varid, &nstart, &ncount, &value), "nc_put_vara_int");
    CHECK(nc_close(ncid), "nc_close");

    CHECK(ncmpi_create(MPI_COMM_WORLD, "pnetcdf.nc", NC_CLOBBER, MPI_INFO_NULL, &ncid), "ncmpi_create");
    CHECK(ncmpi_def_dim(ncid, "x", 2, &dimid), "ncmpi_def_dim");
    CHECK(ncmpi_def_var(ncid, "v", NC_INT, 1, &dimid, &varid), "ncmpi_def_var");
    CHECK(ncmpi_enddef(ncid), "ncmpi_enddef");
    CHECK(ncmpi_put_vara_int_all(ncid, varid, &start, &count, &value), "ncmpi_put_vara_int_all");
    CHECK(ncmpi_close(ncid), "ncmpi_close");

    MPI_Finalize();
    return 0;
}
C
# shellcheck disable=SC2046
mpicc par.c -o par $(nc-config --cflags) -I"$PARALLEL_NETCDF_ROOT/include" \
    $(nc-config --libs) -L"$PARALLEL_NETCDF_ROOT/lib" -Wl,-rpath -Wl,"$PARALLEL_NETCDF_ROOT/lib" -lpnetcdf
mpirun -n 2 ./par
ncdump hdf5.nc | grep 'v = 0, 1' >/dev/null
ncmpidump pnetcdf.nc | grep 'v = 0, 1' >/dev/null

step "LAPACK (${E3SM_LAPACK}): solve a 2x2 system from Fortran"
cat > la.f90 <<'F90'
program la
    implicit none
    double precision :: a(2, 2), b(2)
    integer :: ipiv(2), info
    a = reshape([2d0, 1d0, 1d0, 3d0], [2, 2])
    b = [3d0, 5d0]
    call dgesv(2, 1, a, 2, ipiv, b, 2, info)
    if (info /= 0 .or. any(abs(b - [0.8d0, 1.4d0]) > 1d-12)) error stop "dgesv gave the wrong answer"
end program la
F90
# shellcheck disable=SC2054  # the commas are linker flags, not array separators
case "$E3SM_LAPACK" in
    openblas*) lapack=(-L"$BLAS_ROOT/lib" -Wl,-rpath -Wl,"$BLAS_ROOT/lib" -lopenblas) ;;
    netlib-lapack*) lapack=(-L"$LAPACK_ROOT/lib64" -L"$LAPACK_ROOT/lib" -Wl,-rpath -Wl,"$LAPACK_ROOT/lib64" -Wl,-rpath -Wl,"$LAPACK_ROOT/lib" -llapack -lblas) ;;
    intel-oneapi-mkl*) lapack=(-qmkl) ;;
    *) echo "no LAPACK link line for $E3SM_LAPACK" >&2; exit 1 ;;
esac
mpifort la.f90 -o la "${lapack[@]}"
./la

step "CMake finds MPI, yaml-cpp, Boost and (Generic) BLAS/LAPACK like E3SM's build"
mkdir cmake-test
cat > cmake-test/CMakeLists.txt <<'CMAKE'
cmake_minimum_required(VERSION 3.18)
project(smoke LANGUAGES C CXX Fortran)
find_package(MPI REQUIRED COMPONENTS C CXX Fortran)
find_package(yaml-cpp REQUIRED)
find_package(Boost REQUIRED)
# What E3SM's build does on ghci-snl, which sets BLA_VENDOR=Generic
set(BLA_VENDOR Generic)
find_package(BLAS REQUIRED)
find_package(LAPACK REQUIRED)
add_executable(smoke main.cpp)
target_link_libraries(smoke PRIVATE MPI::MPI_CXX yaml-cpp::yaml-cpp Boost::headers)
CMAKE
cat > cmake-test/main.cpp <<'CPP'
#include <mpi.h>
#include <yaml-cpp/yaml.h>
#include <boost/algorithm/string/trim.hpp>
#include <string>
int main(int argc, char **argv) {
    MPI_Init(&argc, &argv);
    std::string value = YAML::Load("key: '  ok  '")["key"].as<std::string>();
    boost::algorithm::trim(value);
    MPI_Finalize();
    return value == "ok" ? 0 : 1;
}
CPP
cmake -S cmake-test -B cmake-build -DCMAKE_C_COMPILER=mpicc -DCMAKE_CXX_COMPILER=mpicxx \
    -DCMAKE_Fortran_COMPILER=mpifort > cmake-build.log 2>&1 || { cat cmake-build.log; exit 1; }
cmake --build cmake-build > cmake-build.log 2>&1 || { cat cmake-build.log; exit 1; }
./cmake-build/smoke

if [ "$E3SM_WITH_DEBUG_TOOLS" = yes ]; then
    step "debug tools"
    gdb --version | sed -n 1p
    valgrind --version
    valgrind --error-exitcode=1 -q /bin/true
fi

if [ "$E3SM_WITH_MOAB" = yes ]; then
    step "MOAB"
    # Where E3SM's ghci-snl machine expects it (MOAB_ROOT)
    ls /projects/e3sm/software/moab/lib/libMOAB.so* >/dev/null
    # iMOAB (the interface E3SM calls) is built into libMOAB, not a library of its own
    test -f /projects/e3sm/software/moab/include/moab/iMOAB.h
    nm -D --defined-only /projects/e3sm/software/moab/lib/libMOAB.so | grep iMOAB_Initialize >/dev/null
    test -x /projects/e3sm/software/moab/bin/mbtempest
    # Link against MOAB the way E3SM's build does: with the exact MOAB_PACKAGE_LIBS its
    # MOABConfig.cmake exports. Every -lfoo in there has to resolve, -L or not.
    moab=/projects/e3sm/software/moab
    config=$(find "$moab"/lib* -name MOABConfig.cmake | sed -n 1p)
    test -n "$config"
    moab_libs=$(sed -n 's/^set *(MOAB_PACKAGE_LIBS "\(.*\)")$/\1/p' "$config")
    test -n "$moab_libs"
    cat > moab.cpp <<'CPP'
#include "moab/iMOAB.h"
int main() { return reinterpret_cast<void *>(&iMOAB_Initialize) ? 0 : 1; }
CPP
    # shellcheck disable=SC2086  # MOAB_PACKAGE_LIBS is a flag list
    mpicxx moab.cpp -o moab-link -I"$moab/include" -L"$moab/lib" -Wl,-rpath -Wl,"$moab/lib" -lMOAB $moab_libs
    ./moab-link
fi

if [ "${EXPECT_CUDA:-}" = yes ]; then
    step "CUDA: compile a kernel (no GPU needed)"
    test "$E3SM_WITH_CUDA" = yes
    nvcc --version | tail -1
    cat > kernel.cu <<'CU'
__global__ void add(int *x) { x[threadIdx.x] += 1; }
int main() { return 0; }
CU
    nvcc kernel.cu -o kernel
fi

echo "ghci smoke checks passed"
