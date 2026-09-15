import os
import unittest
from unittest.mock import patch

from kubeapp.manifests import application_to_kubernetes_manifests, persistent_volume_claim_name
from kubeapp.models import Application

from .helpers import (
    _container,
    _example,
    _manifests,
    _pod_spec,
    _single_container_manifests,
    _storage_manifests,
)


class EnvironmentManifestTests(unittest.TestCase):
    def test_renders_literal_value(self) -> None:
        manifests = _single_container_manifests(
            environment=[{"name": "APP_ENV", "value": "production"}],
        )

        self.assertEqual(
            _container(manifests)["env"],
            [{"name": "APP_ENV", "value": "production"}],
        )

    def test_renders_secret_source(self) -> None:
        manifests = _single_container_manifests(
            environment=[
                {
                    "name": "DATABASE_URL",
                    "secret": {"name": "catalog-db", "key": "url"},
                }
            ],
        )

        self.assertEqual(
            _container(manifests)["env"],
            [
                {
                    "name": "DATABASE_URL",
                    "valueFrom": {"secretKeyRef": {"name": "catalog-db", "key": "url"}},
                }
            ],
        )

    def test_renders_config_source(self) -> None:
        manifests = _single_container_manifests(
            environment=[
                {
                    "name": "APP_CONFIG",
                    "config": {"name": "catalog-config", "key": "config"},
                }
            ],
        )

        self.assertEqual(
            _container(manifests)["env"],
            [
                {
                    "name": "APP_CONFIG",
                    "valueFrom": {
                        "configMapKeyRef": {
                            "name": "catalog-config",
                            "key": "config",
                        }
                    },
                }
            ],
        )

    def test_omits_env_when_no_environment_is_declared(self) -> None:
        self.assertNotIn("env", _container(_single_container_manifests()))

    def test_does_not_generate_secret_or_config_objects(self) -> None:
        manifests = _single_container_manifests(
            environment=[
                {
                    "name": "DATABASE_URL",
                    "secret": {"name": "catalog-db", "key": "url"},
                },
                {
                    "name": "APP_CONFIG",
                    "config": {"name": "catalog-config", "key": "config"},
                },
            ],
        )

        self.assertEqual(
            [manifest["kind"] for manifest in manifests],
            ["Deployment", "Service"],
        )


class MountManifestTests(unittest.TestCase):
    def test_renders_config_mount(self) -> None:
        manifests = _single_container_manifests(
            mounts=[
                {
                    "name": "catalog-config",
                    "config": {"name": "catalog-config"},
                    "path": "/etc/catalog",
                }
            ],
        )

        self.assertEqual(
            _pod_spec(manifests)["volumes"],
            [
                {
                    "name": "catalog-config",
                    "configMap": {"name": "catalog-config"},
                }
            ],
        )
        self.assertEqual(
            _container(manifests)["volumeMounts"],
            [{"name": "catalog-config", "mountPath": "/etc/catalog"}],
        )

    def test_renders_secret_mount(self) -> None:
        manifests = _single_container_manifests(
            mounts=[
                {
                    "name": "catalog-tls",
                    "secret": {"name": "catalog-tls"},
                    "path": "/etc/catalog/tls",
                }
            ],
        )

        self.assertEqual(
            _pod_spec(manifests)["volumes"],
            [
                {
                    "name": "catalog-tls",
                    "secret": {"secretName": "catalog-tls"},
                }
            ],
        )

    def test_renders_storage_mount(self) -> None:
        manifests = _manifests(
            containers=[
                {
                    "name": "app",
                    "image": "app:1.0",
                    "mounts": [{"name": "data", "storage": "data", "path": "/data"}],
                }
            ],
            storage=[{"name": "data", "size": "10Gi"}],
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

    def test_shared_mount_becomes_one_volume(self) -> None:
        manifests = _manifests(
            containers=[
                {
                    "name": "app",
                    "image": "app:1.0",
                    "mounts": [
                        {
                            "name": "catalog-config",
                            "config": {"name": "catalog-config"},
                            "path": "/etc/catalog",
                        }
                    ],
                },
                {
                    "name": "sidecar",
                    "image": "sidecar:1.0",
                    "mounts": [
                        {
                            "name": "catalog-config",
                            "config": {"name": "catalog-config"},
                            "path": "/config",
                        }
                    ],
                },
            ],
            service={"port": 8080, "container": "app"},
        )
        pod_spec = _pod_spec(manifests)

        self.assertEqual(
            pod_spec["volumes"],
            [
                {
                    "name": "catalog-config",
                    "configMap": {"name": "catalog-config"},
                }
            ],
        )
        self.assertEqual(
            [
                container["volumeMounts"][0]["mountPath"]
                for container in pod_spec["containers"]
            ],
            ["/etc/catalog", "/config"],
        )

    def test_omits_volumes_when_nothing_is_mounted(self) -> None:
        manifests = _single_container_manifests()

        self.assertNotIn("volumes", _pod_spec(manifests))
        self.assertNotIn("volumeMounts", _container(manifests))


class StorageManifestTests(unittest.TestCase):
    def test_generates_claim(self) -> None:
        manifests = _storage_manifests(
            [{"name": "data", "size": "10Gi", "storageClass": "fast"}],
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
                    "storageClassName": "fast",
                    "resources": {"requests": {"storage": "10Gi"}},
                },
            },
        )

    def test_omits_storage_class_when_not_requested(self) -> None:
        manifests = _storage_manifests([{"name": "data", "size": "10Gi"}])

        self.assertNotIn("storageClassName", manifests[0]["spec"])

    def test_propagates_access_modes(self) -> None:
        manifests = _storage_manifests(
            [
                {
                    "name": "data",
                    "size": "10Gi",
                    "accessModes": ["ReadWriteMany", "ReadOnlyMany"],
                }
            ],
        )

        self.assertEqual(
            manifests[0]["spec"]["accessModes"],
            ["ReadWriteMany", "ReadOnlyMany"],
        )

    def test_generates_one_claim_per_storage_definition(self) -> None:
        manifests = _storage_manifests(
            [
                {"name": "data", "size": "10Gi"},
                {"name": "cache", "size": "1Gi"},
            ],
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

    def test_claim_name_is_deterministic(self) -> None:
        first = _storage_manifests([{"name": "data", "size": "10Gi"}])
        second = _storage_manifests([{"name": "data", "size": "10Gi"}])

        self.assertEqual(
            first[0]["metadata"]["name"],
            persistent_volume_claim_name("catalog", "data"),
        )
        self.assertEqual(
            first[0]["metadata"]["name"],
            second[0]["metadata"]["name"],
        )

    def test_deployment_references_the_generated_claim(self) -> None:
        manifests = _storage_manifests([{"name": "data", "size": "10Gi"}])
        claim = manifests[0]

        self.assertEqual(
            _pod_spec(manifests)["volumes"][0]["persistentVolumeClaim"],
            {"claimName": claim["metadata"]["name"]},
        )

    def test_does_not_generate_a_persistent_volume(self) -> None:
        manifests = _storage_manifests(
            [{"name": "data", "size": "10Gi", "storageClass": "fast"}],
        )

        self.assertNotIn(
            "PersistentVolume",
            [manifest["kind"] for manifest in manifests],
        )


class IntentResourceManifestTests(unittest.TestCase):
    def test_inline_environment_substitution(self):
        for field, kind, data_key in (
            ("configuration", "ConfigMap", "data"),
            ("secrets", "Secret", "stringData"),
        ):
            with self.subTest(field=field):
                application = Application.model_validate({
                    "name": "worker",
                    "containers": [{"name": "worker", "image": "worker:1"}],
                    field: [{"name": "settings", "data": {"KEY": "prefix-${QA_VALUE}-${QA_VALUE}"}}],
                })
                with patch.dict(os.environ, {"QA_VALUE": "resolved"}, clear=True):
                    manifests = application_to_kubernetes_manifests(application)
                resource = next(m for m in manifests if m["kind"] == kind)
                self.assertEqual(resource[data_key], {"KEY": "prefix-resolved-resolved"})
                with patch.dict(os.environ, {}, clear=True):
                    with self.assertRaisesRegex(ValueError, "Missing environment variable 'QA_VALUE'"):
                        application_to_kubernetes_manifests(application)

    def test_mount_read_only_semantics(self):
        manifests = application_to_kubernetes_manifests(_example("medium/app.yaml"))
        mounts = {m["mountPath"]: m for m in _container(manifests)["volumeMounts"]}
        self.assertIs(mounts["/etc/catalog"]["readOnly"], True)
        self.assertIs(mounts["/etc/catalog/secrets"]["readOnly"], True)
        self.assertNotIn("readOnly", mounts["/data"])

    def test_partial_resource_ranges(self):
        for bound, rendered in (("min", "requests"), ("max", "limits")):
            for resource, quantity in (("cpu", "250m"), ("memory", "128Mi")):
                with self.subTest(bound=bound, resource=resource):
                    application = Application.model_validate({
                        "name": "worker",
                        "containers": [{
                            "name": "worker", "image": "worker:1",
                            "resources": {resource: {bound: quantity}},
                        }],
                    })
                    manifests = application_to_kubernetes_manifests(application)
                    self.assertEqual(_container(manifests)["resources"], {rendered: {resource: quantity}})
