#!/usr/bin/env python3
"""Run pip check, allowing only the verified cuSPARSELt 0.8.1 ARM metadata defect."""

from email.parser import Parser
from importlib import metadata
import os
import platform
import subprocess
import sys


PACKAGE = "nvidia-cusparselt-cu13"
VERSION = "0.8.1"
DIAGNOSTIC = f"{PACKAGE} {VERSION} is not supported on this platform"
BROKEN_TAG = "py3-none-manylinux2014_sbsa"


def known_metadata_defect(result):
    # Do not suppress other errors, unexpected exit codes, or additional diagnostics.
    if result.returncode != 1 or result.stdout.strip() != DIAGNOSTIC:
        return False
    if (
        os.environ.get("EXPECT_CUDA") != "yes"
        or platform.system() != "Linux"
        or platform.machine() != "aarch64"
    ):
        return False
    try:
        distribution = metadata.distribution(PACKAGE)
        wheel_text = distribution.read_text("WHEEL")
    except (metadata.PackageNotFoundError, OSError, UnicodeError):
        return False
    if distribution.version != VERSION or not wheel_text:
        return False
    wheel = Parser().parsestr(wheel_text)
    return not wheel.defects and wheel.get_all("Tag", []) == [BROKEN_TAG]


def main():
    result = subprocess.run(
        [sys.executable, "-m", "pip", "check"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    print(result.stdout, end="" if result.stdout.endswith("\n") else "\n", flush=True)
    if result.returncode == 0:
        return 0
    if known_metadata_defect(result):
        # Verified against NVIDIA's wheel linked by the cu130 index:
        # https://download.pytorch.org/whl/cu130/nvidia-cusparselt-cu13/
        # Its filename says manylinux2014_aarch64, but WHEEL says manylinux2014_sbsa.
        # Remove this exception when the pinned Torch dependency ships corrected metadata.
        print(
            "WARNING: allowing only the verified nvidia-cusparselt-cu13 0.8.1 "
            "ARM wheel metadata defect (manylinux2014_sbsa). "
            "Package files are unchanged; runtime smoke tests must still pass. "
            "GPU execution is not validated on this runner.",
            file=sys.stderr,
        )
        return 0
    return result.returncode if result.returncode > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
