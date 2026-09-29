# The builtin boost recipe, plus one fix for b2's install step.
#
# b2 `install` writes bin.v2/tools/boost_install/BoostConfigVersion.cmake without first making
# sure that directory exists, so with gcc it fails depending on how the parallel build happens
# to be scheduled. Creating the directory up front removes that race. (With the intel toolset
# the install fails the same way even so, for a reason not yet understood; the intel env
# builds boost with gcc instead.)
import os

from spack_repo.builtin.packages.boost.package import Boost as BuiltinBoost

from spack.package import *


class Boost(BuiltinBoost):
    def install(self, spec, prefix):
        mkdirp(os.path.join(self.stage.source_path, "bin.v2", "tools", "boost_install"))
        super().install(spec, prefix)
