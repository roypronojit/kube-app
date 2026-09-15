"""Renderer boundary and compatibility regressions."""

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from kubeapp.manifests import application_to_kubernetes_manifests
from kubeapp.models import LegacyApplication
from kubeapp.parser import load_application
from kubeapp.renderers import KubernetesRenderer, Renderer


class RendererTests(unittest.TestCase):
    def test_kubernetes_examples_preserve_output_and_application(self):
        root = Path(__file__).resolve().parents[2]
        renderer: Renderer[list[dict]] = KubernetesRenderer()
        for name in ("basic", "medium", "advanced"):
            with self.subTest(example=name), patch.dict(
                os.environ, {"CATALOG_API_KEY": "example-api-key"}
            ):
                directory = root / "examples" / name
                application = load_application(directory / "app.yaml")
                before = application.model_dump()
                expected = application_to_kubernetes_manifests(application, directory)
                self.assertEqual(renderer.render(application, directory), expected)
                self.assertEqual(renderer.render(application, str(directory)), expected)
                self.assertEqual(application.model_dump(), before)

    def test_default_base_directory_and_legacy_compatibility(self):
        application = LegacyApplication.model_validate({
            "apiVersion": "kubeapp.dev/v1alpha1",
            "kind": "Application",
            "metadata": {"name": "catalog"},
            "spec": {"image": "nginx"},
        })
        self.assertEqual(
            KubernetesRenderer().render(application),
            application_to_kubernetes_manifests(application),
        )

    def test_file_input_errors_propagate(self):
        root = Path(__file__).resolve().parents[2]
        application = load_application(root / "examples/advanced/app.yaml")
        with self.assertRaises((ValueError, OSError)):
            KubernetesRenderer().render(application, root / "missing-input-directory")
