import unittest

from kubeapp.manifests import application_to_kubernetes_manifests

from .helpers import (
    _container,
    _example,
    _manifests,
    _output,
    _pod_spec,
    _service,
    _single_container_manifests,
)


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
                    "mounts": [{"name": "data", "storage": "data", "path": "/data"}],
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
                    "mounts": [{"name": "data", "storage": "data", "path": "/data"}],
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
                    "valueFrom": {"secretKeyRef": {"name": "catalog-db", "key": "url"}},
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
