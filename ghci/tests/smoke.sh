#!/bin/bash
# Run as the image's default user, under a login shell:
# docker run --rm -i IMAGE bash -l -s < ghci/tests/smoke.sh
set -euo pipefail

test "$(id -u)" -ne 0
test -n "$SPACK_ARCH"
test "$VIRTUAL_ENV" = /projects/e3sm/software/eamxx-venv
test -w "$VIRTUAL_ENV/lib"
cmake --version
mpirun --version
nc-config --version
nf-config --version
python3 -m pip check
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
print("MPI:", MPI.Get_library_version())
print("Torch:", torch.__version__, "CUDA build:", torch.version.cuda)
PY

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cat > "$work/hello.c" <<'C'
#include <mpi.h>
int main(int argc, char **argv) {
    int count;
    MPI_Init(&argc, &argv);
    MPI_Comm_size(MPI_COMM_WORLD, &count);
    MPI_Finalize();
    return count == 2 ? 0 : 1;
}
C
mpicc "$work/hello.c" -o "$work/hello"
mpirun -n 2 "$work/hello"
cat > "$work/hello.f90" <<'F90'
program hello
    implicit none
    print *, "Fortran compiler works"
end program hello
F90
mpifort "$work/hello.f90" -o "$work/hello-fortran"
"$work/hello-fortran"
echo "ghci smoke checks passed"
