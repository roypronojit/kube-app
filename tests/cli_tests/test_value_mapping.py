"""Declared chart contracts and lossless mapping diagnostics."""

import io
import json
import os
import sys
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch

import yaml

from kubeapp.chart_inspection import inspect_chart
from kubeapp.cli import main
from kubeapp.models import Application
from kubeapp.renderers import HelmRenderer
from kubeapp.value_mapping import compare_values, discover_contract, MappingStatus
from .helpers import temporary_chart


class ValueMappingTests(unittest.TestCase):
    def setUp(self):
        self.chart = temporary_chart(self)
        self.application = Application.model_validate({
            "name": "worker", "replicas": 3,
            "containers": [{"name": "web", "image": "nginx:1.27"}],
            "storage": {"name": "data", "size": "1Gi"},
            "secrets": [{"name": "credentials", "data": {"TOKEN": "${MAPPING_TOKEN}"}}],
        })

    def inspect(self):
        return inspect_chart(self.chart, self.application)

    def values_file(self, values):
        (self.chart / "values.yaml").write_text(yaml.safe_dump(values), encoding="utf-8")

    def schema_file(self, schema):
        (self.chart / "values.schema.json").write_text(json.dumps(schema), encoding="utf-8")

    def test_values_only_nested_paths(self):
        self.values_file({"replicaCount": 1, "image": {"repository": "nginx", "tag": "latest"},
                          "resources": {"requests": {"cpu": "100m"}}})
        contract = discover_contract(self.inspect())
        self.assertTrue(contract.explicit)
        for path in (("replicaCount",), ("image", "repository"), ("image", "tag"),
                     ("resources", "requests", "cpu")):
            self.assertEqual(contract.status(path), MappingStatus.SUPPORTED)
        self.assertEqual(contract.status(("image", "pullPolicy")), MappingStatus.UNSUPPORTED)
        self.assertEqual(contract.status(("service", "port")), MappingStatus.UNSUPPORTED)

    def test_schema_only_nested_paths(self):
        self.schema_file({"properties": {"service": {"properties": {"port": {"type": "integer"}}},
                                         "image": {"properties": {"repository": {"type": "string"}}}}})
        contract = discover_contract(self.inspect())
        self.assertEqual(contract.status(("service", "port")), MappingStatus.SUPPORTED)
        self.assertEqual(contract.status(("image", "repository")), MappingStatus.SUPPORTED)
        self.assertEqual(contract.status(("image", "tag")), MappingStatus.UNSUPPORTED)

    def test_contract_union(self):
        self.values_file({"image": {"repository": "nginx"}})
        self.schema_file({"properties": {"image": {"properties": {"tag": {}}}}})
        contract = discover_contract(self.inspect())
        self.assertEqual(contract.status(("image", "repository")), MappingStatus.SUPPORTED)
        self.assertEqual(contract.status(("image", "tag")), MappingStatus.SUPPORTED)
        self.assertEqual(contract.status(("replicaCount",)), MappingStatus.UNSUPPORTED)

    def test_absent_or_uninformative_schema_contract_is_unknown(self):
        for schema in (None, {}, {"type": "object"}):
            with self.subTest(schema=schema):
                if schema is not None:
                    self.schema_file(schema)
                result = compare_values({"replicaCount": 3}, self.inspect())
                self.assertEqual(result.diagnostics[0].status, MappingStatus.UNKNOWN)

    def test_unresolved_schema_branches_are_unknown(self):
        self.schema_file({"properties": {"image": {"$ref": "#/definitions/image"}}})
        contract = discover_contract(self.inspect())
        self.assertEqual(contract.status(("image",)), MappingStatus.SUPPORTED)
        self.assertEqual(contract.status(("image", "repository")), MappingStatus.UNKNOWN)
        self.assertEqual(contract.status(("replicaCount",)), MappingStatus.UNSUPPORTED)

    def test_diagnostics_do_not_remap_or_filter_values(self):
        self.values_file({"deployment": {"replicas": 1}, "image": {"repository": "nginx"}})
        values = {"replicaCount": 3, "image": {"repository": "nginx", "tag": "1.27"}}
        before = yaml.safe_dump(values)
        result = compare_values(values, self.inspect())
        by_path = {note.generated_path: note for note in result.diagnostics}
        self.assertEqual(by_path[("replicaCount",)].status, MappingStatus.UNSUPPORTED)
        self.assertEqual(by_path[("replicaCount",)].capability, "replicas")
        self.assertIn("mapping is unavailable", by_path[("replicaCount",)].reason)
        self.assertEqual(by_path[("image", "repository")].status, MappingStatus.SUPPORTED)
        self.assertEqual(by_path[("image", "tag")].status, MappingStatus.UNSUPPORTED)
        self.assertEqual(yaml.safe_dump(result.values), before)
        self.assertEqual(yaml.safe_dump(values), before)
        self.assertNotIn("deployment", result.values)

    def test_capability_notes_retained_once_and_secrets_not_in_diagnostics(self):
        self.values_file({"replicaCount": 1})
        with patch.dict(os.environ, {"MAPPING_TOKEN": "resolved-private-token"}):
            values = HelmRenderer().render(self.application)
        inspection = self.inspect()
        result = compare_values(values, inspection)
        self.assertEqual(result.capability_notes, inspection.notes)
        self.assertEqual(sum(note.capability == "storage" for note in result.capability_notes), 1)
        secret_notes = [note for note in result.diagnostics if note.capability == "secrets"]
        self.assertTrue(secret_notes)
        self.assertNotIn("resolved-private-token", repr(result))
        self.assertNotIn("resolved-private-token", repr(secret_notes))

    def test_cli_keeps_values_and_does_not_present_diagnostics(self):
        self.values_file({"deployment": {"replicas": 1}})
        before = self.application.model_dump()
        output, errors = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, {"MAPPING_TOKEN": "resolved-private-token"}), patch(
            "kubeapp.cli.load_application", return_value=self.application
        ), patch("kubeapp.cli.compare_values", wraps=compare_values) as compare, patch.object(
            sys, "argv", ["kube-app", "render", "app.yaml", "-f", "helm", "-c", str(self.chart)]
        ), redirect_stdout(output), redirect_stderr(errors):
            expected = HelmRenderer().render(self.application)
            self.assertEqual(main(), 0)
            compare.assert_called_once()
        self.assertEqual(errors.getvalue(), "")
        self.assertEqual(yaml.safe_load(output.getvalue()), expected)
        self.assertEqual(self.application.model_dump(), before)

    def test_kubernetes_does_not_use_value_contract(self):
        with patch.dict(os.environ, {"MAPPING_TOKEN": "resolved-private-token"}), patch(
            "kubeapp.cli.load_application", return_value=self.application
        ), patch("kubeapp.cli.compare_values", side_effect=AssertionError("Unexpected mapping")) as compare, patch.object(
            sys, "argv", ["kube-app", "render", "app.yaml"]
        ), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(main(), 0)
            compare.assert_not_called()
