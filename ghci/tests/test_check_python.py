"""Regression coverage for the narrowly scoped pip-check exception; no CUDA needed."""

from contextlib import redirect_stderr, redirect_stdout
from importlib import metadata
import io
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import check_python


class CheckPythonTests(unittest.TestCase):
    def run_check(self, *, output=check_python.DIAGNOSTIC + "\n", code=1,
                  system="Linux", machine="aarch64", cuda="yes", version="0.8.1",
                  wheel="Wheel-Version: 1.0\nTag: py3-none-manylinux2014_sbsa\n",
                  metadata_error=None):
        distribution = Mock(version=version)
        distribution.read_text.return_value = wheel
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            patch.object(check_python.subprocess, "run", return_value=SimpleNamespace(
                returncode=code, stdout=output,
            )) as run,
            patch.object(check_python.platform, "system", return_value=system),
            patch.object(check_python.platform, "machine", return_value=machine),
            patch.dict(check_python.os.environ, {"EXPECT_CUDA": cuda}),
            patch.object(check_python.metadata, "distribution", return_value=distribution,
                         side_effect=metadata_error) as lookup,
            redirect_stdout(stdout), redirect_stderr(stderr),
        ):
            status = check_python.main()
        run.assert_called_once_with(
            [check_python.sys.executable, "-m", "pip", "check"],
            stdout=check_python.subprocess.PIPE,
            stderr=check_python.subprocess.STDOUT,
            text=True,
            check=False,
        )
        return status, stdout.getvalue(), stderr.getvalue(), lookup

    def test_success_needs_no_exception(self):
        status, output, warning, lookup = self.run_check(
            code=0, output="No broken requirements found.\n",
        )
        self.assertEqual(status, 0)
        self.assertIn("No broken requirements", output)
        self.assertEqual(warning, "")
        lookup.assert_not_called()

    def test_verified_defect_warns_and_preserves_pip_output(self):
        status, output, warning, lookup = self.run_check()
        self.assertEqual(status, 0)
        self.assertEqual(output, check_python.DIAGNOSTIC + "\n")
        self.assertIn("WARNING:", warning)
        self.assertIn("runtime smoke tests must still pass", warning)
        lookup.assert_called_once_with(check_python.PACKAGE)

    def test_other_failures_are_not_suppressed(self):
        cases = {
            "extra dependency error": {"output": check_python.DIAGNOSTIC + "\nfoo requires bar\n"},
            "extra warning": {"output": "WARNING: unexpected\n" + check_python.DIAGNOSTIC},
            "duplicate error": {"output": (check_python.DIAGNOSTIC + "\n") * 2},
            "different package": {"output": "other 0.8.1 is not supported on this platform\n"},
            "unexpected status": {"code": 2},
            "signal": {"code": -9},
            "empty output": {"output": ""},
            "x86": {"machine": "x86_64"},
            "other OS": {"system": "Darwin"},
            "CPU image": {"cuda": "no"},
            "unset CUDA expectation": {"cuda": ""},
            "different version": {"version": "0.9.1"},
            "corrected metadata": {"wheel": "Tag: py3-none-manylinux2014_aarch64\n"},
            "additional tag": {"wheel": "Tag: py3-none-manylinux2014_sbsa\nTag: py3-none-any\n"},
            "no metadata": {"wheel": None},
            "empty metadata": {"wheel": ""},
            "malformed metadata": {"wheel": "broken header\nTag: py3-none-manylinux2014_sbsa\n"},
            "missing package": {"metadata_error": metadata.PackageNotFoundError()},
            "unreadable metadata": {"metadata_error": OSError("unreadable")},
        }
        for name, kwargs in cases.items():
            with self.subTest(name=name):
                status, _, warning, _ = self.run_check(**kwargs)
                self.assertNotEqual(status, 0)
                self.assertEqual(warning, "")


if __name__ == "__main__":
    unittest.main()
