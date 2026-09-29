# The builtin boost recipe, plus one fix for b2's install step.
#
# b2 `install` writes bin.v2/tools/boost_install/BoostConfigVersion.cmake without first making
# sure that directory exists. With the intel toolset it never does, and the install fails after
# every library has been built; with gcc it depends on how the parallel build happens to be
# scheduled. Creating the directory up front removes the race for every compiler.
import os

from spack_repo.builtin.packages.boost.package import Boost as BuiltinBoost

from spack.package import *


class Boost(BuiltinBoost):
    def install(self, spec, prefix):
        mkdirp(os.path.join(self.stage.source_path, "bin.v2", "tools", "boost_install"))
        super().install(spec, prefix)
