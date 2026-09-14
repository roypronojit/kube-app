import unittest

from kubeapp.generators import application_to_helm_values
from kubeapp.models import LegacyApplication as Application


class ApplicationToHelmValuesTests(unittest.TestCase):
    def test_maps_all_supported_fields(self) -> None:
        application = Application.model_validate(
            {
                "apiVersion": "kubeapp.dev/v1alpha1",
                "kind": "Application",
                "metadata": {"name": "catalog"},
                "spec": {
                    "image": "registry.example.com/catalog:1.2.3",
                    "service": {"port": 8080},
                    "resources": {
                        "requests": {"cpu": "100m", "memory": "128Mi"},
                        "limits": {"cpu": "500m"},
                    },
                    "scaling": {
                        "min_replicas": 2,
                        "max_replicas": 5,
                    },
                },
            }
        )

        values = application_to_helm_values(application)

        self.assertEqual(
            values,
            {
                "name": "catalog",
                "image": {
                    "repository": "registry.example.com/catalog",
                    "tag": "1.2.3",
                },
                "service": {"port": 8080},
                "resources": {
                    "requests": {"cpu": "100m", "memory": "128Mi"},
                    "limits": {"cpu": "500m"},
                },
                "scaling": {"minReplicas": 2, "maxReplicas": 5},
            },
        )

    def test_omits_optional_values_and_defaults_untagged_image(self) -> None:
        application = Application.model_validate(
            {
                "apiVersion": "kubeapp.dev/v1alpha1",
                "kind": "Application",
                "metadata": {"name": "catalog"},
                "spec": {"image": "nginx"},
            }
        )

        values = application_to_helm_values(application)

        self.assertEqual(
            values,
            {
                "name": "catalog",
                "image": {"repository": "nginx", "tag": "latest"},
            },
        )

    def test_rejects_applications_that_define_containers(self) -> None:
        application = Application.model_validate(
            {
                "apiVersion": "kubeapp.dev/v1alpha1",
                "kind": "Application",
                "metadata": {"name": "catalog"},
                "spec": {
                    "containers": [
                        {"name": "catalog", "image": "catalog:1.0"},
                    ],
                },
            }
        )

        with self.assertRaises(ValueError):
            application_to_helm_values(application)

    def test_preserves_registry_port_in_untagged_image(self) -> None:
        application = Application.model_validate(
            {
                "apiVersion": "kubeapp.dev/v1alpha1",
                "kind": "Application",
                "metadata": {"name": "catalog"},
                "spec": {"image": "registry.example.com:5000/catalog"},
            }
        )

        values = application_to_helm_values(application)

        self.assertEqual(
            values["image"],
            {
                "repository": "registry.example.com:5000/catalog",
                "tag": "latest",
            },
        )
