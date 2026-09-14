import unittest
from unittest.mock import patch

from kubeapp.manifests import application_to_kubernetes_manifests

from .helpers import PROJECT_ROOT, _example, _output


class AdvancedExampleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.application = _example("advanced/app.yaml")
        with patch.dict("os.environ", {"CATALOG_API_KEY": "example-api-key"}):
            self.manifests = application_to_kubernetes_manifests(
                self.application, PROJECT_ROOT / "examples" / "advanced"
            )
        self.claim, self.deployment, self.service = self.manifests[-3:]
        self.pod_spec = self.deployment["spec"]["template"]["spec"]

    def test_example_matches_generated_manifests(self) -> None:
        self.assertEqual(_output("advanced/rendered.yaml"), self.manifests)

    def test_generates_claim_deployment_and_service_in_order(self) -> None:
        self.assertEqual(
            [manifest["kind"] for manifest in self.manifests],
            [
                "ConfigMap",
                "ConfigMap",
                "Secret",
                "Secret",
                "PersistentVolumeClaim",
                "Deployment",
                "Service",
            ],
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
