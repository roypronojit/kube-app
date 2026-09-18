"""CLI stream separation, diagnostic severity, and output failure safety."""

import io
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from unittest.mock import patch

import yaml

from kubeapp.cli import main
from kubeapp.chart_inspection import inspect_chart
from kubeapp.diagnostics import helm_messages
from kubeapp.models import Application
from kubeapp.renderers import HelmRenderer, KubernetesRenderer
from kubeapp.value_mapping import compare_values
from .helpers import temporary_chart


class DiagnosticCliTests(unittest.TestCase):
    def setUp(self):
        self.chart = temporary_chart(self)
        self.source = self.chart / "app.yaml"
        self.data = {"name": "worker", "containers": [{"name": "web", "image": "nginx:1"}],
                     "secrets": [{"name": "credentials", "data": {"TOKEN": "${DIAGNOSTIC_TOKEN}"}}]}
        self.source.write_text(yaml.safe_dump(self.data), encoding="utf-8")
        self.application = Application.model_validate(self.data)
        self.env = patch.dict("os.environ", {"DIAGNOSTIC_TOKEN": "resolved-sensitive-token"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def invoke(self, *arguments):
        out, err = io.StringIO(), io.StringIO()
        with patch.object(sys, "argv", ["kube-app", "render", str(self.source), *arguments]), redirect_stdout(out), redirect_stderr(err):
            result = main()
        return result, out.getvalue(), err.getvalue()

    def helm(self, *arguments):
        return self.invoke("-f", "helm", "-c", str(self.chart), *arguments)

    def test_unknown_and_capability_messages_only_on_stderr(self):
        result, output, errors = self.helm()
        self.assertEqual(result, 0)
        self.assertEqual(yaml.safe_load(output), HelmRenderer().render(self.application))
        self.assertIn("NOTE:", errors)
        self.assertIn("could not be determined", errors)
        self.assertIn('WARNING: Application capability "secrets"', errors)
        self.assertNotIn("created", errors)
        self.assertNotIn("resolved-sensitive-token", errors)
        self.assertNotIn("WARNING:", output)
        self.assertNotIn("NOTE:", output)

    def test_unsupported_warning_and_clean_output_file(self):
        (self.chart / "values.yaml").write_text("deployment:\n  replicas: 1\n")
        result, output, errors = self.helm()
        self.assertEqual(result, 0)
        self.assertIn('WARNING: Generated value path "replicaCount" is not declared', errors)
        destination = self.chart / "output" / "values.yaml"
        written = self.helm("-o", str(destination))
        self.assertEqual(written, (0, "", errors))
        self.assertEqual(destination.read_text(encoding="utf-8"), output)
        self.assertEqual(yaml.safe_load(output)["replicaCount"], 1)
        self.assertNotIn("resolved-sensitive-token", errors)

    def test_supported_mappings_are_silent(self):
        values = HelmRenderer().render(self.application)
        (self.chart / "values.yaml").write_text(yaml.safe_dump(values), encoding="utf-8")
        templates = self.chart / "templates"
        templates.mkdir()
        (templates / "resources.yaml").write_text("kind: Deployment\n---\nkind: Secret\n")
        result, output, errors = self.helm()
        self.assertEqual((result, errors), (0, ""))
        self.assertEqual(yaml.safe_load(output), values)

    def test_duplicate_and_descendant_messages_are_suppressed(self):
        (self.chart / "values.yaml").write_text("{}\n")
        mapping = compare_values(HelmRenderer().render(self.application), inspect_chart(self.chart, self.application))
        repeated = replace(mapping, diagnostics=mapping.diagnostics * 2, capability_notes=mapping.capability_notes * 2)
        messages = helm_messages(repeated)
        self.assertEqual(messages, helm_messages(mapping))
        self.assertEqual(len(messages), len(set(messages)))
        self.assertEqual(sum('value path "image"' in message for message in messages), 1)
        self.assertFalse(any('value path "image.repository"' in message for message in messages))

    def test_failure_preserves_file_and_emits_no_yaml(self):
        destination = self.chart / "output.yaml"
        for failure in ("invalid-chart", "invalid-application", "generation", "write"):
            with self.subTest(failure=failure):
                destination.write_bytes(b"existing\n")
                self.source.write_text(yaml.safe_dump(self.data), encoding="utf-8")
                if failure == "invalid-application":
                    self.source.write_text("name: worker\ncontainers: []\n")
                if failure == "generation":
                    data = dict(self.data, containers=[{"name": "web", "image": "nginx@sha256:abcd"}])
                    self.source.write_text(yaml.safe_dump(data), encoding="utf-8")
                if failure == "invalid-chart":
                    result = self.invoke("-f", "helm", "-c", str(self.chart / "absent"), "-o", str(destination))
                elif failure == "write":
                    with patch("kubeapp.cli.os.replace", side_effect=OSError("write blocked")):
                        result = self.helm("-o", str(destination))
                else:
                    result = self.helm("-o", str(destination))
                self.assertEqual(result[0], 1)
                self.assertEqual(result[1], "")
                self.assertIn("failed:", result[2])
                self.assertNotIn("resolved-sensitive-token", result[2])
                self.assertEqual(destination.read_bytes(), b"existing\n")
                self.assertEqual(list(self.chart.glob(".output.yaml.*")), [])

    def test_kubernetes_stdout_and_file_are_unchanged_and_quiet(self):
        result, output, errors = self.invoke()
        self.assertEqual((result, errors), (0, ""))
        self.assertEqual(list(yaml.safe_load_all(output)), KubernetesRenderer().render(self.application))
        destination = self.chart / "manifests.yaml"
        self.assertEqual(self.invoke("--output", str(destination)), (0, "", ""))
        self.assertEqual(destination.read_text(encoding="utf-8"), output)

    def test_help_describes_current_contract(self):
        for option in ("-h", "--help"):
            output = io.StringIO()
            with patch.object(sys, "argv", ["kube-app", "render", option]), redirect_stdout(output), self.assertRaises(SystemExit) as raised:
                main()
            self.assertEqual(raised.exception.code, 0)
            text = " ".join(output.getvalue().split())
            for fragment in ("--format", "--name", "--chart", "--output", "--help", "default: kubernetes",
                             "Helm values YAML", "--chart is required for Helm", "Helm executable is not required"):
                self.assertIn(fragment, text)
            for option in ("--strict", "--verbose", "--renderer"):
                self.assertNotIn(option, text)
