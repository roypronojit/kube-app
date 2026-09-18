"""Failure diagnostics from the packaged-binary smoke driver."""

import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts.smoke_binary import smoke


class SmokeDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.binary = Path(directory.name) / "kube-app"
        content = b"\x7fELFfake executable"
        self.binary.write_bytes(content)
        self.binary.with_name("kube-app.sha256").write_text(
            f"{hashlib.sha256(content).hexdigest()}  kube-app\n", encoding="ascii"
        )

    def test_unexpected_exit_reports_stderr_locally_and_in_container(self):
        for container_image in (None, "ubuntu:22.04"):
            with self.subTest(container_image=container_image):
                error = "error while loading shared libraries: libz.so.1\n"
                failed = subprocess.CompletedProcess([], 127, stdout="", stderr=error)
                with patch("scripts.smoke_binary.subprocess.run", return_value=failed), \
                     self.assertRaises(AssertionError) as raised:
                    smoke(self.binary, container_image)
                self.assertIn("Unexpected exit code 127", str(raised.exception))
                self.assertIn("--help", str(raised.exception))
                self.assertIn(error, str(raised.exception))

    def test_secret_leak_is_not_echoed_in_failure_diagnostics(self):
        failed = subprocess.CompletedProcess(
            [], 1, stdout="", stderr="leaked smoke-placeholder-token\n"
        )
        with patch("scripts.smoke_binary.subprocess.run", return_value=failed), \
             self.assertRaises(AssertionError) as raised:
            smoke(self.binary)
        self.assertEqual(str(raised.exception), "Secret leaked to stderr")
