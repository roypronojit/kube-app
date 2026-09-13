from pathlib import Path
import unittest

import yaml

from kubeapp.manifests import (
    application_to_kubernetes_manifests,
    persistent_volume_claim_name,
)
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

    def test_application_without_new_capabilities_is_unchanged(self) -> None:
        manifests = _manifests()
        container = _container(manifests)

        self.assertEqual(
            [manifest["kind"] for manifest in manifests],
            ["Deployment", "Service"],
        )
        self.assertNotIn("env", container)
        self.assertNotIn("volumeMounts", container)
        self.assertNotIn("volumes", _pod_spec(manifests))


class EnvironmentManifestTests(unittest.TestCase):
    def test_renders_simple_values(self) -> None:
        manifests = _manifests(
            environment={"APP_ENV": "production", "LOG_LEVEL": "info"},
        )

        self.assertEqual(
            _container(manifests)["env"],
            [
                {"name": "APP_ENV", "value": "production"},
                {"name": "LOG_LEVEL", "value": "info"},
            ],
        )

    def test_renders_secret_reference(self) -> None:
        manifests = _manifests(secrets={"DATABASE_URL": "catalog-db"})

        self.assertEqual(
            _container(manifests)["env"],
            [
                {
                    "name": "DATABASE_URL",
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": "catalog-db",
                            "key": "DATABASE_URL",
                        }
                    },
                }
            ],
        )

    def test_renders_configuration_reference(self) -> None:
        manifests = _manifests(
            configuration={"APP_CONFIG": "catalog-config"},
        )

        self.assertEqual(
            _container(manifests)["env"],
            [
                {
                    "name": "APP_CONFIG",
                    "valueFrom": {
                        "configMapKeyRef": {
                            "name": "catalog-config",
                            "key": "APP_CONFIG",
                        }
                    },
                }
            ],
        )

    def test_orders_environment_then_secrets_then_configuration(self) -> None:
        manifests = _manifests(
            environment={"APP_ENV": "production"},
            secrets={"DATABASE_URL": "catalog-db"},
            configuration={"APP_CONFIG": "catalog-config"},
        )

        self.assertEqual(
            [entry["name"] for entry in _container(manifests)["env"]],
            ["APP_ENV", "DATABASE_URL", "APP_CONFIG"],
        )

    def test_does_not_generate_secret_or_configuration_objects(self) -> None:
        manifests = _manifests(
            secrets={"DATABASE_URL": "catalog-db"},
            configuration={"APP_CONFIG": "catalog-config"},
        )

        self.assertEqual(
            [manifest["kind"] for manifest in manifests],
            ["Deployment", "Service"],
        )


class StorageManifestTests(unittest.TestCase):
    def test_omits_claim_when_storage_is_absent(self) -> None:
        manifests = _manifests()

        self.assertEqual(
            [manifest["kind"] for manifest in manifests],
            ["Deployment", "Service"],
        )

    def test_generates_claim(self) -> None:
        manifests = _manifests(
            storage={"data": {"size": "10Gi", "path": "/data"}},
        )

        self.assertEqual(
            manifests[0],
            {
                "apiVersion": "v1",
                "kind": "PersistentVolumeClaim",
                "metadata": {
                    "name": "catalog-data",
                    "labels": {"app.kubernetes.io/name": "catalog"},
                },
                "spec": {
                    "accessModes": ["ReadWriteOnce"],
                    "resources": {"requests": {"storage": "10Gi"}},
                },
            },
        )

    def test_propagates_size(self) -> None:
        manifests = _manifests(
            storage={"data": {"size": "250Mi", "path": "/data"}},
        )

        self.assertEqual(
            manifests[0]["spec"]["resources"]["requests"]["storage"],
            "250Mi",
        )

    def test_claim_name_is_deterministic(self) -> None:
        first = _manifests(
            storage={"data": {"size": "10Gi", "path": "/data"}},
        )
        second = _manifests(
            storage={"data": {"size": "10Gi", "path": "/data"}},
        )

        self.assertEqual(
            first[0]["metadata"]["name"],
            persistent_volume_claim_name("catalog", "data"),
        )
        self.assertEqual(
            first[0]["metadata"]["name"],
            second[0]["metadata"]["name"],
        )

    def test_wires_storage_into_the_deployment(self) -> None:
        manifests = _manifests(
            storage={"data": {"size": "10Gi", "path": "/data"}},
        )

        self.assertEqual(
            _pod_spec(manifests)["volumes"],
            [
                {
                    "name": "data",
                    "persistentVolumeClaim": {"claimName": "catalog-data"},
                }
            ],
        )
        self.assertEqual(
            _container(manifests)["volumeMounts"],
            [{"name": "data", "mountPath": "/data"}],
        )

    def test_generates_one_claim_per_storage_entry_in_order(self) -> None:
        manifests = _manifests(
            storage={
                "data": {"size": "10Gi", "path": "/data"},
                "cache": {"size": "1Gi", "path": "/cache"},
            },
        )

        self.assertEqual(
            [manifest["kind"] for manifest in manifests],
            [
                "PersistentVolumeClaim",
                "PersistentVolumeClaim",
                "Deployment",
                "Service",
            ],
        )
        self.assertEqual(
            [manifest["metadata"]["name"] for manifest in manifests[:2]],
            ["catalog-data", "catalog-cache"],
        )
        self.assertEqual(
            _container(manifests)["volumeMounts"],
            [
                {"name": "data", "mountPath": "/data"},
                {"name": "cache", "mountPath": "/cache"},
            ],
        )


class ConfigurationAndStorageExampleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.project_root = Path(__file__).resolve().parents[1]
        application_data = yaml.safe_load(
            (
                self.project_root
                / "examples"
                / "configuration-and-storage.yaml"
            ).read_text(encoding="utf-8")
        )
        self.application = Application.model_validate(application_data)
        self.manifests = application_to_kubernetes_manifests(self.application)

    def test_example_matches_generated_manifests(self) -> None:
        output_manifests = list(
            yaml.safe_load_all(
                (
                    self.project_root
                    / "output"
                    / "configuration-and-storage-manifest.yaml"
                ).read_text(encoding="utf-8")
            )
        )

        self.assertEqual(output_manifests, self.manifests)

    def test_generates_claim_deployment_and_service_in_order(self) -> None:
        self.assertEqual(
            [manifest["kind"] for manifest in self.manifests],
            ["PersistentVolumeClaim", "Deployment", "Service"],
        )

    def test_deployment_mounts_the_generated_claim(self) -> None:
        claim, deployment, _ = self.manifests
        pod_spec = deployment["spec"]["template"]["spec"]
        container = pod_spec["containers"][0]

        self.assertEqual(
            pod_spec["volumes"],
            [
                {
                    "name": "data",
                    "persistentVolumeClaim": {
                        "claimName": claim["metadata"]["name"],
                    },
                }
            ],
        )
        self.assertEqual(
            [mount["name"] for mount in container["volumeMounts"]],
            [volume["name"] for volume in pod_spec["volumes"]],
        )

    def test_deployment_environment_covers_every_declared_setting(
        self,
    ) -> None:
        _claim, deployment, _service = self.manifests
        container = deployment["spec"]["template"]["spec"]["containers"][0]

        self.assertEqual(
            container["env"],
            [
                {"name": "APP_ENV", "value": "production"},
                {"name": "LOG_LEVEL", "value": "info"},
                {
                    "name": "DATABASE_URL",
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": "catalog-db",
                            "key": "DATABASE_URL",
                        }
                    },
                },
                {
                    "name": "APP_CONFIG",
                    "valueFrom": {
                        "configMapKeyRef": {
                            "name": "catalog-config",
                            "key": "APP_CONFIG",
                        }
                    },
                },
            ],
        )

    def test_service_targets_the_deployment_pods(self) -> None:
        _claim, deployment, service = self.manifests

        self.assertEqual(
            service["spec"]["selector"],
            deployment["spec"]["template"]["metadata"]["labels"],
        )


def _manifests(**spec_fields: object) -> list[dict[str, object]]:
    application_data: dict[str, object] = {
        "apiVersion": "kubeapp.dev/v1alpha1",
        "kind": "Application",
        "metadata": {"name": "catalog"},
        "spec": {
            "image": "catalog:1.0",
            "service": {"port": 8080},
        },
    }
    application_data["spec"].update(spec_fields)

    return application_to_kubernetes_manifests(
        Application.model_validate(application_data)
    )


def _deployment(manifests: list[dict[str, object]]) -> dict[str, object]:
    return next(
        manifest
        for manifest in manifests
        if manifest["kind"] == "Deployment"
    )


def _pod_spec(manifests: list[dict[str, object]]) -> dict[str, object]:
    return _deployment(manifests)["spec"]["template"]["spec"]


def _container(manifests: list[dict[str, object]]) -> dict[str, object]:
    return _pod_spec(manifests)["containers"][0]
