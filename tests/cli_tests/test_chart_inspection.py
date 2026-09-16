"""External chart inspection and CLI rules, with temporary fixtures only."""

import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from kubeapp.chart_inspection import inspect_chart
from kubeapp.cli import main
from kubeapp.models import Application


class ChartInspectionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.chart = self.base / "external"
        self.chart.mkdir()
        (self.chart / "Chart.yaml").write_text("apiVersion: v2\nname: external\nversion: 1.0.0\n")
        (self.chart / "templates").mkdir()
        self.application = Application.model_validate({
            "name": "app", "containers": [{"name": "web", "image": "nginx:1"}],
            "service": {"port": 80},
            "configuration": [{"name": "config", "data": {"KEY": "value"}}],
            "secrets": [{"name": "secret", "data": {"KEY": "value"}}],
            "storage": {"name": "data", "size": "1Gi"},
        })

    def template(self, content, filename="unrelated.txt"):
        (self.chart / "templates" / filename).write_text(content, encoding="utf-8")

    def test_valid_chart_and_optional_configuration(self):
        (self.chart / "values.yaml").write_text("enabled: false\n")
        (self.chart / "values.schema.json").write_text('{"type": "object"}')
        result = inspect_chart(self.chart, self.application)
        self.assertEqual(result.path, self.chart.resolve())
        self.assertEqual(result.metadata["name"], "external")
        self.assertEqual(result.values, {"enabled": False})
        self.assertEqual(result.values_schema, {"type": "object"})

    def test_invalid_chart_paths(self):
        empty = self.base / "empty"
        empty.mkdir()
        for path, message in ((self.base / "missing", "does not exist"),
                              (self.chart / "Chart.yaml", "not a directory"),
                              (empty, "Chart.yaml is missing")):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, message):
                inspect_chart(path, self.application)

    def test_all_resource_kinds_detected_by_content(self):
        kinds = {"Deployment", "Service", "ConfigMap", "Secret", "PersistentVolumeClaim"}
        for kind in kinds:
            with self.subTest(kind=kind):
                self.template(f"apiVersion: v1\nkind: {kind}\n")
                self.assertEqual(inspect_chart(self.chart, self.application).detected_kinds, {kind})
        self.template("\n---\n".join(f"kind: {kind}" for kind in kinds))
        self.assertEqual(inspect_chart(self.chart, self.application).notes, ())

    def test_filenames_comments_and_nested_data_do_not_supply_kinds(self):
        self.template('# kind: Deployment\ndata:\n  kind: Secret\n{{/* kind: Service */}}\n', "persistentvolumeclaim.yaml")
        self.assertEqual(inspect_chart(self.chart, self.application).detected_kinds, set())

    def test_conditional_and_literal_template_kinds(self):
        self.template('''{{- if .Values.enabled }}
kind: Deployment
{{- end }}
---
kind: {{ "Service" }}
---
kind: {{ if .Values.flag }}ConfigMap{{ else }}Secret{{ end }}
---
kind: 'PersistentVolumeClaim'
''')
        self.assertEqual(inspect_chart(self.chart, self.application).notes, ())

    def test_dynamic_kind_is_unknown_even_when_values_suggest_kind(self):
        (self.chart / "values.yaml").write_text("kind: Deployment\n")
        self.template("kind: {{ .Values.kind }}\n")
        result = inspect_chart(self.chart, self.application)
        self.assertEqual(result.detected_kinds, set())
        self.assertEqual({note.capability for note in result.notes},
                         {"workload", "service", "configuration", "secrets", "storage"})
        note = next(note for note in result.notes if note.capability == "storage")
        self.assertEqual(note.expected_kind, "PersistentVolumeClaim")
        self.assertIn('Application capability "storage" could not be mapped', note.message)
        self.assertNotIn("created", note.message)

    def test_only_requested_capabilities_have_notes_and_model_is_unchanged(self):
        application = Application.model_validate({"name": "app", "containers": [{"name": "web", "image": "nginx:1"}]})
        before = application.model_dump()
        result = inspect_chart(self.chart, application)
        self.assertEqual([note.capability for note in result.notes], ["workload"])
        self.assertEqual(application.model_dump(), before)

    def test_relative_path_uses_working_directory(self):
        previous = Path.cwd()
        try:
            os.chdir(self.base)
            self.assertEqual(inspect_chart("external", self.application).path, self.chart.resolve())
        finally:
            os.chdir(previous)

    def invoke(self, *arguments):
        output, errors = io.StringIO(), io.StringIO()
        with (patch.object(sys, "argv", ["kube-app", "render", "app.yaml", *arguments]),
              patch("kubeapp.cli.load_application", return_value=self.application),
              redirect_stdout(output), redirect_stderr(errors)):
            result = main()
        return result, output.getvalue(), errors.getvalue()

    def test_helm_requires_chart_for_both_aliases(self):
        for alias in ("helm", "h"):
            with self.subTest(alias=alias), self.assertRaises(SystemExit) as raised:
                self.invoke("-f", alias)
            self.assertEqual(raised.exception.code, 2)

    def test_kubernetes_needs_no_chart_and_rejects_chart(self):
        for arguments in ((), ("-f", "kubernetes"), ("-f", "k8s"), ("-f", "k")):
            with self.subTest(arguments=arguments):
                self.assertEqual(self.invoke(*arguments)[0], 0)
                with self.assertRaises(SystemExit) as raised:
                    self.invoke(*arguments, "--chart", str(self.chart))
                self.assertEqual(raised.exception.code, 2)

    def test_chart_options_inspect_without_changing_helm_output(self):
        for option in ("-c", "--chart"):
            with self.subTest(option=option), patch("kubeapp.cli.inspect_chart", wraps=inspect_chart) as inspection, patch(
                "kubeapp.cli._render_helm", return_value="existing Helm output\n"
            ) as render:
                self.assertEqual(self.invoke("-f", "h", option, str(self.chart)), (0, "existing Helm output\n", ""))
                inspection.assert_called_once_with(str(self.chart), self.application)
                self.assertEqual(render.call_args.args[:2], (self.application, Path("app.yaml").resolve().parent))
                self.assertEqual(render.call_args.args[2].path, self.chart.resolve())

    def test_invalid_chart_preserves_output_and_does_not_render(self):
        destination = self.base / "output.yaml"
        destination.write_text("existing")
        with patch("kubeapp.cli._render_helm") as render:
            result, output, errors = self.invoke("-f", "helm", "-c", str(self.base / "missing"), "-o", str(destination))
        self.assertEqual((result, output), (1, ""))
        self.assertIn("Chart path does not exist", errors)
        self.assertEqual(destination.read_text(), "existing")
        render.assert_not_called()
