import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from kubeapp.manifests import (
    application_to_kubernetes_manifests,
    persistent_volume_claim_name,
)
from kubeapp.models import Application as IntentApplication
from kubeapp.models import LegacyApplication as Application

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class LegacyApplicationTests(unittest.TestCase):
    def test_basic_example_matches_generated_manifests(self) -> None:
        application = _example("basic/app.yaml")

        manifests = application_to_kubernetes_manifests(application)

        self.assertEqual(_output("basic/rendered.yaml"), manifests)

    def test_omits_service_when_not_specified(self) -> None:
        manifests = _manifests(image="worker:1.0", name="worker")

        self.assertEqual(len(manifests), 1)
        self.assertEqual(manifests[0]["kind"], "Deployment")
        self.assertEqual(manifests[0]["spec"]["replicas"], 1)

    def test_single_image_form_creates_one_container(self) -> None:
        manifests = _manifests(
            image="nginx:1.27",
            service={"port": 80},
            resources={"requests": {"cpu": "100m"}},
        )
        container = _container(manifests)

        self.assertEqual(container["name"], "catalog")
        self.assertEqual(container["image"], "nginx:1.27")
        self.assertEqual(container["resources"], {"requests": {"cpu": "100m"}})
        self.assertEqual(
            container["ports"],
            [{"name": "http", "containerPort": 80, "protocol": "TCP"}],
        )

    def test_pod_spec_has_nothing_extra(self) -> None:
        pod_spec = _pod_spec(_manifests(image="nginx:1.27"))

        self.assertEqual(list(pod_spec), ["containers"])


class ContainerManifestTests(unittest.TestCase):
    def test_renders_containers_in_declared_order(self) -> None:
        manifests = _manifests(
            containers=[
                {"name": "app", "image": "app:1.0"},
                {"name": "sidecar", "image": "sidecar:1.0"},
            ],
            service={"port": 8080, "container": "app"},
        )

        self.assertEqual(
            [c["name"] for c in _pod_spec(manifests)["containers"]],
            ["app", "sidecar"],
        )

    def test_resources_stay_on_their_own_container(self) -> None:
        manifests = _manifests(
            containers=[
                {
                    "name": "app",
                    "image": "app:1.0",
                    "resources": {"limits": {"memory": "256Mi"}},
                },
                {"name": "sidecar", "image": "sidecar:1.0"},
            ],
            service={"port": 8080, "container": "app"},
        )
        containers = _pod_spec(manifests)["containers"]

        self.assertEqual(
            containers[0]["resources"],
            {"limits": {"memory": "256Mi"}},
        )
        self.assertNotIn("resources", containers[1])


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
                    "valueFrom": {
                        "secretKeyRef": {"name": "catalog-db", "key": "url"}
                    },
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
                    "mounts": [
                        {"name": "data", "storage": "data", "path": "/data"}
                    ],
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


class ServiceManifestTests(unittest.TestCase):
    def test_defaults_to_cluster_ip(self) -> None:
        manifests = _single_container_manifests()

        self.assertEqual(_service(manifests)["spec"]["type"], "ClusterIP")

    def test_renders_node_port(self) -> None:
        manifests = _manifests(
            containers=[{"name": "app", "image": "app:1.0"}],
            service={"type": "NodePort", "port": 8080},
        )

        self.assertEqual(_service(manifests)["spec"]["type"], "NodePort")

    def test_renders_load_balancer(self) -> None:
        manifests = _manifests(
            containers=[{"name": "app", "image": "app:1.0"}],
            service={"type": "LoadBalancer", "port": 8080},
        )

        self.assertEqual(
            _service(manifests)["spec"]["ports"],
            [
                {
                    "name": "http",
                    "port": 8080,
                    "targetPort": "http",
                    "protocol": "TCP",
                }
            ],
        )

    def test_only_the_named_container_exposes_the_port(self) -> None:
        manifests = _manifests(
            containers=[
                {"name": "app", "image": "app:1.0"},
                {"name": "sidecar", "image": "sidecar:1.0"},
            ],
            service={"port": 8080, "container": "sidecar"},
        )
        containers = _pod_spec(manifests)["containers"]

        self.assertNotIn("ports", containers[0])
        self.assertEqual(
            containers[1]["ports"],
            [{"name": "http", "containerPort": 8080, "protocol": "TCP"}],
        )
        self.assertEqual(
            _service(manifests)["spec"]["ports"][0]["targetPort"],
            "http",
        )

    def test_no_container_exposes_a_port_without_a_service(self) -> None:
        manifests = _manifests(
            containers=[{"name": "app", "image": "app:1.0"}],
        )

        self.assertNotIn("ports", _pod_spec(manifests)["containers"][0])


class InitContainerManifestTests(unittest.TestCase):
    def test_renders_init_container(self) -> None:
        manifests = _manifests(
            containers=[{"name": "app", "image": "app:1.0"}],
            initContainers=[{"name": "migrate", "image": "migrate:1.0"}],
        )

        self.assertEqual(
            _pod_spec(manifests)["initContainers"],
            [{"name": "migrate", "image": "migrate:1.0"}],
        )

    def test_renders_multiple_init_containers_in_order(self) -> None:
        manifests = _manifests(
            containers=[{"name": "app", "image": "app:1.0"}],
            initContainers=[
                {"name": "migrate", "image": "migrate:1.0"},
                {"name": "seed", "image": "seed:1.0"},
            ],
        )

        self.assertEqual(
            [c["name"] for c in _pod_spec(manifests)["initContainers"]],
            ["migrate", "seed"],
        )

    def test_renders_init_container_environment_and_mounts(self) -> None:
        manifests = _manifests(
            containers=[
                {
                    "name": "app",
                    "image": "app:1.0",
                    "mounts": [
                        {"name": "data", "storage": "data", "path": "/data"}
                    ],
                }
            ],
            initContainers=[
                {
                    "name": "migrate",
                    "image": "migrate:1.0",
                    "environment": [
                        {
                            "name": "DATABASE_URL",
                            "secret": {"name": "catalog-db", "key": "url"},
                        }
                    ],
                    "mounts": [
                        {"name": "data", "storage": "data", "path": "/data"}
                    ],
                }
            ],
            storage=[{"name": "data", "size": "10Gi"}],
        )
        init_container = _pod_spec(manifests)["initContainers"][0]

        self.assertEqual(
            init_container["env"],
            [
                {
                    "name": "DATABASE_URL",
                    "valueFrom": {
                        "secretKeyRef": {"name": "catalog-db", "key": "url"}
                    },
                }
            ],
        )
        self.assertEqual(
            init_container["volumeMounts"],
            [{"name": "data", "mountPath": "/data"}],
        )
        self.assertEqual(len(_pod_spec(manifests)["volumes"]), 1)

    def test_init_containers_never_expose_the_service_port(self) -> None:
        manifests = _manifests(
            containers=[{"name": "app", "image": "app:1.0"}],
            initContainers=[{"name": "migrate", "image": "migrate:1.0"}],
            service={"port": 8080},
        )

        self.assertNotIn("ports", _pod_spec(manifests)["initContainers"][0])

    def test_omits_init_containers_when_none_are_declared(self) -> None:
        self.assertNotIn(
            "initContainers",
            _pod_spec(_single_container_manifests()),
        )


class ServiceAccountManifestTests(unittest.TestCase):
    def test_renders_service_account_name(self) -> None:
        manifests = _manifests(
            containers=[{"name": "app", "image": "app:1.0"}],
            serviceAccount={"name": "catalog"},
        )

        self.assertEqual(
            _pod_spec(manifests)["serviceAccountName"],
            "catalog",
        )

    def test_omits_service_account_when_not_requested(self) -> None:
        self.assertNotIn(
            "serviceAccountName",
            _pod_spec(_single_container_manifests()),
        )

    def test_does_not_generate_a_service_account_object(self) -> None:
        manifests = _manifests(
            containers=[{"name": "app", "image": "app:1.0"}],
            serviceAccount={"name": "catalog"},
        )

        self.assertEqual(
            [manifest["kind"] for manifest in manifests],
            ["Deployment"],
        )


class AdvancedExampleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.application = _example("advanced/app.yaml")
        with patch.dict("os.environ", {"CATALOG_API_KEY": "example-api-key"}):
            self.manifests = application_to_kubernetes_manifests(self.application, PROJECT_ROOT / "examples" / "advanced")
        self.claim, self.deployment, self.service = self.manifests[-3:]
        self.pod_spec = self.deployment["spec"]["template"]["spec"]

    def test_example_matches_generated_manifests(self) -> None:
        self.assertEqual(_output("advanced/rendered.yaml"), self.manifests)

    def test_generates_claim_deployment_and_service_in_order(self) -> None:
        self.assertEqual(
            [manifest["kind"] for manifest in self.manifests],
            ["ConfigMap", "ConfigMap", "Secret", "Secret", "PersistentVolumeClaim", "Deployment", "Service"],
        )

    def test_deployment_runs_the_init_container_then_the_containers(
        self,
    ) -> None:
        self.assertEqual(
            [c["name"] for c in self.pod_spec["initContainers"]],
            ["database-migration"],
        )
        self.assertEqual(
            [c["name"] for c in self.pod_spec["containers"]],
            ["catalog", "metrics"],
        )

    def test_service_targets_the_catalog_container_port(self) -> None:
        catalog, metrics = self.pod_spec["containers"]

        self.assertEqual(
            catalog["ports"],
            [{"name": "http", "containerPort": 8080, "protocol": "TCP"}],
        )
        self.assertNotIn("ports", metrics)
        self.assertEqual(
            self.service["spec"]["ports"][0]["targetPort"],
            catalog["ports"][0]["name"],
        )
        self.assertEqual(self.service["spec"]["type"], "LoadBalancer")
        self.assertEqual(
            self.service["spec"]["selector"],
            self.deployment["spec"]["template"]["metadata"]["labels"],
        )

    def test_every_volume_mount_resolves_to_a_pod_volume(self) -> None:
        volume_names = {volume["name"] for volume in self.pod_spec["volumes"]}
        containers = [
            *self.pod_spec["initContainers"],
            *self.pod_spec["containers"],
        ]

        for container in containers:
            for mount in container.get("volumeMounts", []):
                with self.subTest(container=container["name"]):
                    self.assertIn(mount["name"], volume_names)

    def test_storage_mount_points_at_the_generated_claim(self) -> None:
        data_volume = next(
            volume
            for volume in self.pod_spec["volumes"]
            if "persistentVolumeClaim" in volume
        )

        self.assertEqual(
            data_volume["persistentVolumeClaim"]["claimName"],
            self.claim["metadata"]["name"],
        )
        self.assertEqual(self.claim["spec"]["storageClassName"], "fast")

    def test_creates_and_consumes_configuration_and_secrets(
        self,
    ) -> None:
        catalog = self.pod_spec["containers"][0]

        self.assertEqual(
            catalog["env"],
            [
                {"name": "APP_ENV", "value": "production"},
                {"name": "LOG_LEVEL", "value": "info"},
            ],
        )
        self.assertEqual(
            catalog["envFrom"],
            [
                {"configMapRef": {"name": "catalog-config"}},
                {"configMapRef": {"name": "catalog-feature-flags"}},
                {"secretRef": {"name": "catalog-db"}},
                {"secretRef": {"name": "catalog-api"}},
            ],
        )
        self.assertEqual(
            {manifest["kind"] for manifest in self.manifests},
            {"ConfigMap", "Secret", "PersistentVolumeClaim", "Deployment", "Service"},
        )

    def test_runs_as_the_requested_service_account(self) -> None:
        self.assertEqual(self.pod_spec["serviceAccountName"], "catalog")


def _example(name: str) -> Application:
    return IntentApplication.model_validate(
        yaml.safe_load(
            (PROJECT_ROOT / "examples" / name).read_text(encoding="utf-8")
        )
    )


def _output(name: str) -> list[dict[str, object]]:
    return list(
        yaml.safe_load_all(
            (PROJECT_ROOT / "examples" / name).read_text(encoding="utf-8")
        )
    )


def _manifests(
    name: str = "catalog",
    **spec_fields: object,
) -> list[dict[str, object]]:
    return application_to_kubernetes_manifests(
        Application.model_validate(
            {
                "apiVersion": "kubeapp.dev/v1alpha1",
                "kind": "Application",
                "metadata": {"name": name},
                "spec": dict(spec_fields),
            }
        )
    )


def _single_container_manifests(
    **container_fields: object,
) -> list[dict[str, object]]:
    container = {"name": "app", "image": "app:1.0"}
    container.update(container_fields)

    return _manifests(containers=[container], service={"port": 8080})


def _storage_manifests(
    storage: list[dict[str, object]],
) -> list[dict[str, object]]:
    mounts = [
        {
            "name": entry["name"],
            "storage": entry["name"],
            "path": f"/{entry['name']}",
        }
        for entry in storage
    ]

    return _manifests(
        containers=[{"name": "app", "image": "app:1.0", "mounts": mounts}],
        storage=storage,
        service={"port": 8080},
    )


def _deployment(manifests: list[dict[str, object]]) -> dict[str, object]:
    return next(
        manifest
        for manifest in manifests
        if manifest["kind"] == "Deployment"
    )


def _service(manifests: list[dict[str, object]]) -> dict[str, object]:
    return next(
        manifest for manifest in manifests if manifest["kind"] == "Service"
    )


def _pod_spec(manifests: list[dict[str, object]]) -> dict[str, object]:
    return _deployment(manifests)["spec"]["template"]["spec"]


def _container(manifests: list[dict[str, object]]) -> dict[str, object]:
    return _pod_spec(manifests)["containers"][0]
