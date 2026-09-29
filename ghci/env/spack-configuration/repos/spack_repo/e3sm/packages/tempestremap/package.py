# The builtin tempestremap recipe, plus the C compiler it needs: its configure checks for a
# working C compiler, but the builtin recipe only declares cxx, so spack never sets CC and the
# check fails ("C compiler cannot create executables"). Drop this once spack-packages fixes it.
from spack_repo.builtin.packages.tempestremap.package import Tempestremap as BuiltinTempestremap

from spack.package import *


class Tempestremap(BuiltinTempestremap):
    depends_on("c", type="build")
