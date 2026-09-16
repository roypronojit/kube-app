"""Focused public CLI contracts with temporary inputs and no Helm binary."""
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch

import yaml

from kubeapp.cli import main
from kubeapp.parser import load_application
from kubeapp.renderers import HelmRenderer, KubernetesRenderer
from .helpers import PROJECT_ROOT, temporary_chart


class CliOutputTests(unittest.TestCase):
    def setUp(self):
        self.chart = temporary_chart(self)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.app_dir = self.base / "application"
        self.app_dir.mkdir()
        self.source = self.app_dir / "app.yaml"
        self.data = {
            "name": "worker", "containers": [{"name": "web", "image": "nginx:1.27"}],
            "configuration": [{"name": "settings", "file": "settings.env"}],
            "secrets": [{"name": "credentials", "file": "credentials.env"},
                        {"name": "inline", "data": {"TOKEN": "${TEST_TOKEN}"}}],
            "service": {"port": 80},
        }
        self.source.write_text(yaml.safe_dump(self.data), encoding="utf-8")
        (self.app_dir / "settings.env").write_text("MODE=test\n", encoding="utf-8")
        (self.app_dir / "credentials.env").write_text("TOKEN=${TEST_TOKEN}\n", encoding="utf-8")
        self.environment = {**os.environ, "TEST_TOKEN": "private-test-value", "PATH": "",
                            "PYTHONPATH": str(PROJECT_ROOT / "src"), "PYTHONDONTWRITEBYTECODE": "1"}

    def invoke(self, alias="helm", *arguments):
        options = ["-f", alias]
        if alias in ("helm", "h"):
            options += ["-c", str(self.chart)]
        return subprocess.run(
            [sys.executable, "-m", "kubeapp", "render", str(self.source), *options, *arguments],
            cwd=self.base, env=self.environment, capture_output=True, text=True, timeout=30,
        )

    def test_helm_aliases_emit_values_without_helm_installed(self):
        for alias in ("helm", "h"):
            with self.subTest(alias=alias):
                result = self.invoke(alias)
                self.assertEqual(result.returncode, 0, result.stderr)
                documents = list(yaml.safe_load_all(result.stdout))
                self.assertEqual(len(documents), 1)
                values = documents[0]
                self.assertIsInstance(values, dict)
                self.assertNotIn("kind", values)
                self.assertNotIn("apiVersion", values)
                self.assertNotRegex(result.stdout, r"(?m)^kind:")
                with patch.dict(os.environ, self.environment, clear=True):
                    expected = HelmRenderer().render(load_application(self.source), self.app_dir)
                self.assertEqual(values, expected)
                self.assertEqual(values["configuration"][0]["data"], {"MODE": "test"})
                for secret in values["secrets"]:
                    self.assertEqual(secret["data"], {"TOKEN": "private-test-value"})

    def test_output_file_matches_stdout_with_name_override(self):
        for option in ("-o", "--output"):
            result = self.invoke("h", "-n", "replacement")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(yaml.safe_load(result.stdout)["name"], "replacement")
            destination = self.base / "output" / "values.yaml"
            written = self.invoke("h", "--name", "replacement", option, str(destination))
            self.assertEqual((written.returncode, written.stdout), (0, ""))
            self.assertEqual(destination.read_text(encoding="utf-8"), result.stdout)

    def test_no_external_commands_or_application_mutation(self):
        application = load_application(self.source)
        before = application.model_dump()
        source_before = self.source.read_bytes()
        for override in ([], ["-n", "replacement"]):
            with patch.dict(os.environ, self.environment, clear=True), patch(
                "kubeapp.cli.load_application", return_value=application
            ), patch("subprocess.run", side_effect=AssertionError("External command invoked")) as run, patch.object(
                sys, "argv", ["kube-app", "render", str(self.source), "-f", "helm", "-c", str(self.chart), *override]
            ), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(main(), 0)
                run.assert_not_called()
            self.assertEqual(application.model_dump(), before)
        self.assertEqual(self.source.read_bytes(), source_before)
        self.assertEqual((self.app_dir / "credentials.env").read_text(), "TOKEN=${TEST_TOKEN}\n")

    def test_failures_preserve_output_and_hide_secrets(self):
        destination = self.base / "values.yaml"
        for failure in ("validation", "missing-variable", "malformed-file", "missing-file", "unsupported"):
            with self.subTest(failure=failure):
                data = yaml.safe_load(yaml.safe_dump(self.data))
                (self.app_dir / "credentials.env").write_text("TOKEN=${TEST_TOKEN}\n", encoding="utf-8")
                if failure == "validation":
                    data["secrets"][1]["data"]["TOKEN"] = {"invalid": "private-test-value"}
                elif failure == "missing-variable":
                    data["secrets"].append({"name": "missing", "data": {"TOKEN": "${ABSENT_TEST_TOKEN}"}})
                elif failure == "malformed-file":
                    (self.app_dir / "credentials.env").write_text("private-test-value\n", encoding="utf-8")
                elif failure == "missing-file":
                    data["secrets"][0]["file"] = "absent.env"
                else:
                    data["service"]["type"] = "NodePort"
                self.environment.pop("ABSENT_TEST_TOKEN", None)
                self.source.write_text(yaml.safe_dump(data), encoding="utf-8")
                destination.write_bytes(b"existing output\n")
                result = self.invoke("helm", "-o", str(destination))
                self.assertEqual((result.returncode, result.stdout), (1, ""))
                self.assertNotIn("private-test-value", result.stderr)
                self.assertIn("failed:", result.stderr)
                self.assertEqual(destination.read_bytes(), b"existing output\n")

    def test_kubernetes_output_unchanged(self):
        with patch.dict(os.environ, self.environment, clear=True):
            expected = KubernetesRenderer().render(load_application(self.source), self.app_dir)
        for alias in ("kubernetes", "k8s", "k"):
            result = self.invoke(alias)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(list(yaml.safe_load_all(result.stdout)), expected)
