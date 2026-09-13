from pathlib import Path
import unittest

import yaml

from kubeapp.manifests import application_to_kubernetes_manifests
from kubeapp.models import Application


class KubernetesManifestTests(unittest.TestCase):
    def test_basic_example_matches_generated_manifests(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        application_data = yaml.safe_load(
            (project_root / "examples" / "basic.yaml").read_text(
                encoding="utf-8",
            )
        )
        application = Application.model_validate(application_data)

        manifests = application_to_kubernetes_manifests(application)

        output_manifests = list(
            yaml.safe_load_all(
                (project_root / "output" / "basic-manifest.yaml").read_text(
                    encoding="utf-8",
                )
            )
        )
        self.assertEqual(output_manifests, manifests)

    def test_omits_service_when_not_specified(self) -> None:
        application = Application.model_validate(
            {
                "apiVersion": "kubeapp.dev/v1alpha1",
                "kind": "Application",
                "metadata": {"name": "worker"},
                "spec": {"image": "worker:1.0"},
            }
        )

        manifests = application_to_kubernetes_manifests(application)

        self.assertEqual(len(manifests), 1)
        self.assertEqual(manifests[0]["kind"], "Deployment")
        self.assertEqual(manifests[0]["spec"]["replicas"], 1)
