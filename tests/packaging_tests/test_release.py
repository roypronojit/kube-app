"""Release guards must fail before an artifact can be published."""

import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location("build_linux", Path(__file__).resolve().parents[2] / "scripts/build_linux.py")
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


class ReleaseVersionTests(unittest.TestCase):
    def test_matching_tag_and_local_build(self):
        version = build.release_version()
        self.assertEqual(build.release_version(f"v{version}"), version)

    def test_mismatched_or_nonrelease_tag_is_rejected(self):
        for tag in ("v9.9.9", "main", "v0.3.0-rc1", "v0.3.0; echo unsafe"):
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                build.release_version(tag)

    def test_runtime_and_package_version_must_match(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src/kubeapp").mkdir(parents=True)
            (root / "pyproject.toml").write_text('[project]\nversion = "0.3.0"\n')
            (root / "src/kubeapp/__init__.py").write_text('__version__ = "0.2.0"\n')
            with patch.object(build, "ROOT", root), self.assertRaises(ValueError):
                build.release_version("v0.3.0")
