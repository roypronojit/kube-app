"""End-to-end checks of the installed public CLI, including real Helm execution."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import yaml

from tests.semantic_helpers import assert_semantically_equal
from .helpers import PROJECT_ROOT


@unittest.skipUnless(shutil.which("helm"), "Helm is required for CLI equivalence")
class CliEquivalenceTests(unittest.TestCase):
    def setUp(self):
        executable = "kube-app.exe" if os.name == "nt" else "kube-app"
        self.cli = Path(sys.executable).parent / executable
        self.assertTrue(self.cli.is_file(), "Install kube-app in the test environment")
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.cwd = Path(self.directory.name)
        self.environment = {**os.environ, "CATALOG_API_KEY": "cli-example-key"}

    def invoke(self, source, *arguments, environment=None):
        return subprocess.run(
            [str(self.cli), "render", str(source), *arguments],
            cwd=self.cwd, env=self.environment if environment is None else environment,
            capture_output=True, text=True, timeout=30,
        )

    def test_examples_stdout_files_defaults_and_aliases(self):
        for example, count in (("basic", 2), ("medium", 5), ("advanced", 7)):
            source = PROJECT_ROOT / "examples" / example / "app.yaml"
            outputs = {}
            for alias in ("kubernetes", "k8s", "k", "helm", "h", None):
                with self.subTest(example=example, alias=alias):
                    arguments = ["-r", alias] if alias else []
                    result = self.invoke(source, *arguments)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stderr, "")
                    documents = list(yaml.safe_load_all(result.stdout))
                    self.assertEqual(len(documents), count)
                    outputs[alias] = result.stdout
                    canonical = "helm" if alias in ("helm", "h") else "kubernetes"
                    # Alias/default selection must preserve even serialized output.
                    self.assertEqual(result.stdout, outputs[canonical])
                    assert_semantically_equal(
                        self, documents, list(yaml.safe_load_all(outputs["kubernetes"]))
                    )

                    destination = Path("output") / example / f"{alias or 'default'}.yaml"
                    option = "--output" if alias in ("helm", "kubernetes") else "-o"
                    written = self.invoke(source, *arguments, option, str(destination))
                    self.assertEqual(written.returncode, 0, written.stderr)
                    self.assertEqual(written.stdout, "")
                    self.assertEqual(written.stderr, "")
                    content = (self.cwd / destination).read_text(encoding="utf-8")
                    self.assertEqual(content, result.stdout)
                    assert_semantically_equal(
                        self, list(yaml.safe_load_all(content)),
                        list(yaml.safe_load_all(outputs["kubernetes"]))
                    )

    def test_failures_leave_no_partial_output(self):
        environment = dict(self.environment)
        environment.pop("CATALOG_API_KEY")
        cases = [
            (renderer, self.cwd / "missing.yaml", self.environment, "Validation failed:")
            for renderer in ("kubernetes", "helm")
        ] + [
            (renderer, PROJECT_ROOT / "examples/advanced/app.yaml", environment, "Render failed:")
            for renderer in ("kubernetes", "helm")
        ] + [
            ("helm", PROJECT_ROOT / "examples/basic/app.yaml",
             {**self.environment, "PATH": str(self.cwd)}, "Render failed:")
        ]
        for index, (renderer, source, env, message) in enumerate(cases):
            for existing in (False, True):
                with self.subTest(renderer=renderer, case=index, existing=existing):
                    destination = self.cwd / f"failure-{index}-{existing}.yaml"
                    if existing:
                        destination.write_bytes(b"existing output\n")
                    result = self.invoke(source, "-r", renderer, "-o", str(destination), environment=env)
                    self.assertEqual(result.returncode, 1, result.stderr)
                    self.assertEqual(result.stdout, "")
                    self.assertIn(message, result.stderr)
                    if existing:
                        self.assertEqual(destination.read_bytes(), b"existing output\n")
                    else:
                        self.assertFalse(destination.exists())
