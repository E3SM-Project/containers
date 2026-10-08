# EAMxx standalone testing (test-all-eamxx, scripts-ctest-driver) on this image, as machine
# "e3sm-container": machines_specs.py imports class Local from ~/.cime/scream_mach_specs.py.
# Its cmake settings are in e3sm-container-eamxx.cmake next to this file.
import pathlib, shutil, subprocess

from machines_specs import Machine

IMAGE_ENV = pathlib.Path("/etc/e3sm/image.env")


def _image_has_cuda():
    return IMAGE_ENV.is_file() and "E3SM_WITH_CUDA=yes" in IMAGE_ENV.read_text().split()


class Local(Machine):
    concrete = True

    @classmethod
    def setup(cls):
        super().setup_base("e3sm-container")
        cls.mach_file = pathlib.Path(__file__).resolve().parent / "e3sm-container-eamxx.cmake"
        cls.baselines_dir = "/projects/e3sm/data/baselines/scream/e3sm-container"
        cls.env_setup = ["export GATOR_INITIAL_MB=4000MB"]
        if _image_has_cuda():
            cls.gpu_arch = "cuda"
            # One resource per GPU; none visible (no driver, or a build-only run) still
            # leaves one, so the build can proceed.
            gpus = 0
            if shutil.which("nvidia-smi"):
                out = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                                     capture_output=True, text=True, check=False).stdout
                gpus = len(out.splitlines())
            cls.num_run_res = max(gpus, 1)
