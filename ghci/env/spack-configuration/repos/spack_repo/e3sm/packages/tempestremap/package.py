# The builtin tempestremap recipe, plus the C compiler it needs: its configure checks for a
# working C compiler, but the builtin recipe only declares cxx, so spack never sets CC and the
# check fails ("C compiler cannot create executables"). Fixed upstream in spack-packages #6076
# (2026-08-14), after the v2026.06.0 release pinned in repos.yaml: delete this override (and
# the e3sm repo, if it is the last one) when that pin moves past the fix.
from spack_repo.builtin.packages.tempestremap.package import Tempestremap as BuiltinTempestremap

from spack.package import *


class Tempestremap(BuiltinTempestremap):
    depends_on("c", type="build")
