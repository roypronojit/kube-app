import unittest

from pydantic import ValidationError

from kubeapp.models import LegacyApplication as Application
from kubeapp.models import Application as IntentApplication, IntentContainer

from .helpers import _application, _application_data, _containers_application, _example


class ApplicationModelTests(unittest.TestCase):
    def test_service_cannot_target_init_container(self):
        with self.assertRaisesRegex(ValidationError, "unknown container"):
            IntentApplication.model_validate({
                "name": "worker",
                "containers": [{"name": "worker", "image": "worker:1"}],
                "init": [{"name": "setup", "image": "setup:1"}],
                "service": {"port": 80, "container": "setup"},
            })

    def test_legacy_application_identity_validation(self):
        _application().validate_application()
        for field, value in (("apiVersion", "kubeapp.dev/v2"), ("kind", "Deployment")):
            with self.subTest(field=field):
                data = _application_data()
                data[field] = value
                application = Application.model_validate(data)
                with self.assertRaisesRegex(ValueError, f"Unsupported {field}"):
                    application.validate_application()

    def test_scaling_defaults_and_equal_bounds(self):
        for scaling, expected in (({}, (1, 1)), ({"min_replicas": 2, "max_replicas": 2}, (2, 2))):
            with self.subTest(scaling=scaling):
                result = _application(scaling=scaling).spec.scaling
                self.assertEqual((result.min_replicas, result.max_replicas), expected)

    def test_accepts_basic_example(self) -> None:
        application = _example("basic/app.yaml")

        self.assertEqual(application.name, "hello-world")
        self.assertEqual(
            application.containers[0].image, "nginxinc/nginx-unprivileged:1.27"
        )
        self.assertEqual(application.replicas, 2)

    def test_accepts_advanced_example(self) -> None:
        application = _example("advanced/app.yaml")

        self.assertEqual(
            [container.name for container in application.containers],
            ["catalog", "metrics"],
        )
        self.assertEqual(
            [c.name for c in application.init],
            ["database-migration"],
        )
        self.assertEqual(application.service.type, "LoadBalancer")
        self.assertEqual(application.service_account, "catalog")

    def test_rejects_name_with_uppercase_or_underscore(self) -> None:
        with self.assertRaises(ValidationError):
            Application.model_validate(_application_data(name="Hello_World"))

    def test_rejects_name_longer_than_63_characters(self) -> None:
        with self.assertRaises(ValidationError):
            Application.model_validate(_application_data(name="a" * 64))

    def test_rejects_unknown_nested_field(self) -> None:
        with self.assertRaises(ValidationError):
            _application(service={"port": 8080, "protocol": "TCP"})

    def test_rejects_invalid_scaling_range(self) -> None:
        with self.assertRaises(ValidationError):
            _application(scaling={"min_replicas": 3, "max_replicas": 2})


class ContainerModelTests(unittest.TestCase):
    def test_image_length_boundary(self):
        self.assertEqual(IntentContainer(name="app", image="a" * 512).image, "a" * 512)
        with self.assertRaises(ValidationError):
            IntentContainer(name="app", image="a" * 513)

    def test_accepts_legacy_single_container_application(self) -> None:
        application = _application()

        self.assertEqual(application.spec.image, "nginx:1.27")
        self.assertEqual(application.spec.containers, [])

    def test_accepts_multiple_containers(self) -> None:
        application = _containers_application(
            containers=[
                {"name": "app", "image": "app:1.0"},
                {"name": "sidecar", "image": "sidecar:1.0"},
            ],
            service={"port": 8080, "container": "app"},
        )

        self.assertEqual(
            [container.name for container in application.spec.containers],
            ["app", "sidecar"],
        )

    def test_rejects_duplicate_container_names(self) -> None:
        with self.assertRaises(ValidationError):
            _containers_application(
                containers=[
                    {"name": "app", "image": "app:1.0"},
                    {"name": "app", "image": "other:1.0"},
                ],
                service={"port": 8080, "container": "app"},
            )

    def test_rejects_init_container_reusing_container_name(self) -> None:
        with self.assertRaises(ValidationError):
            _containers_application(
                containers=[{"name": "app", "image": "app:1.0"}],
                initContainers=[{"name": "app", "image": "migrate:1.0"}],
            )

    def test_rejects_init_container_reusing_application_name(self) -> None:
        with self.assertRaises(ValidationError):
            _application(
                initContainers=[{"name": "hello-world", "image": "migrate:1.0"}],
            )

    def test_rejects_invalid_container_names(self) -> None:
        for name in ["", "App", "my_app", "-app", "a" * 64]:
            with self.subTest(name=name):
                with self.assertRaises(ValidationError):
                    _containers_application(
                        containers=[{"name": name, "image": "app:1.0"}],
                    )

    def test_rejects_invalid_images(self) -> None:
        for image in ["", "my image:1.0", "/app:1.0", "-app"]:
            with self.subTest(image=image):
                with self.assertRaises(ValidationError):
                    _containers_application(
                        containers=[{"name": "app", "image": image}],
                    )

    def test_rejects_application_without_any_container(self) -> None:
        with self.assertRaises(ValidationError):
            Application.model_validate(
                {
                    "apiVersion": "kubeapp.dev/v1alpha1",
                    "kind": "Application",
                    "metadata": {"name": "hello-world"},
                    "spec": {"service": {"port": 8080}},
                }
            )

    def test_rejects_both_image_and_containers(self) -> None:
        with self.assertRaises(ValidationError):
            _application(containers=[{"name": "app", "image": "app:1.0"}])

    def test_rejects_spec_resources_with_containers(self) -> None:
        with self.assertRaises(ValidationError):
            _containers_application(
                containers=[{"name": "app", "image": "app:1.0"}],
                resources={"requests": {"cpu": "100m"}},
            )

    def test_accepts_resources_on_a_container(self) -> None:
        application = _containers_application(
            containers=[
                {
                    "name": "app",
                    "image": "app:1.0",
                    "resources": {"requests": {"cpu": "100m"}},
                },
                {"name": "sidecar", "image": "sidecar:1.0"},
            ],
            service={"port": 8080, "container": "app"},
        )

        self.assertEqual(
            application.spec.containers[0].resources.requests.cpu,
            "100m",
        )
        self.assertIsNone(application.spec.containers[1].resources)


class ServiceModelTests(unittest.TestCase):
    def test_defaults_to_cluster_ip(self) -> None:
        application = _application(service={"port": 80})

        self.assertEqual(application.spec.service.type, "ClusterIP")
        self.assertIsNone(application.spec.service.container)

    def test_accepts_node_port(self) -> None:
        application = _application(service={"type": "NodePort", "port": 80})

        self.assertEqual(application.spec.service.type, "NodePort")

    def test_accepts_load_balancer(self) -> None:
        application = _application(
            service={"type": "LoadBalancer", "port": 80},
        )

        self.assertEqual(application.spec.service.type, "LoadBalancer")

    def test_rejects_invalid_service_type(self) -> None:
        with self.assertRaises(ValidationError):
            _application(service={"type": "Ingress", "port": 80})

    def test_rejects_invalid_port(self) -> None:
        for port in [0, -1, 70000, "eighty"]:
            with self.subTest(port=port):
                with self.assertRaises(ValidationError):
                    _application(service={"port": port})

    def test_requires_a_target_container_when_several_are_defined(
        self,
    ) -> None:
        with self.assertRaises(ValidationError):
            _containers_application(
                containers=[
                    {"name": "app", "image": "app:1.0"},
                    {"name": "sidecar", "image": "sidecar:1.0"},
                ],
                service={"port": 8080},
            )

    def test_rejects_unknown_target_container(self) -> None:
        with self.assertRaises(ValidationError):
            _containers_application(
                containers=[{"name": "app", "image": "app:1.0"}],
                service={"port": 8080, "container": "missing"},
            )

    def test_rejects_target_container_with_the_image_shorthand(self) -> None:
        with self.assertRaises(ValidationError):
            _application(service={"port": 8080, "container": "hello-world"})

    def test_accepts_a_single_container_without_naming_it(self) -> None:
        application = _containers_application(
            containers=[{"name": "app", "image": "app:1.0"}],
            service={"port": 8080},
        )

        self.assertIsNone(application.spec.service.container)


class ServiceAccountModelTests(unittest.TestCase):
    def test_accepts_service_account(self) -> None:
        application = _application(serviceAccount={"name": "catalog"})

        self.assertEqual(application.spec.service_account.name, "catalog")

    def test_defaults_to_no_service_account(self) -> None:
        self.assertIsNone(_application().spec.service_account)

    def test_rejects_invalid_service_account_names(self) -> None:
        for name in ["", "Catalog", "catalog_sa", "-catalog"]:
            with self.subTest(name=name):
                with self.assertRaises(ValidationError):
                    _application(serviceAccount={"name": name})

    def test_rejects_unknown_service_account_field(self) -> None:
        with self.assertRaises(ValidationError):
            _application(serviceAccount={"name": "catalog", "create": True})


class InitContainerModelTests(unittest.TestCase):
    def test_accepts_init_container(self) -> None:
        application = _application(
            initContainers=[{"name": "migrate", "image": "migrate:1.0"}],
        )

        self.assertEqual(application.spec.init_containers[0].name, "migrate")

    def test_accepts_multiple_init_containers(self) -> None:
        application = _application(
            initContainers=[
                {"name": "migrate", "image": "migrate:1.0"},
                {"name": "seed", "image": "seed:1.0"},
            ],
        )

        self.assertEqual(len(application.spec.init_containers), 2)

    def test_rejects_duplicate_init_container_names(self) -> None:
        with self.assertRaises(ValidationError):
            _application(
                initContainers=[
                    {"name": "migrate", "image": "migrate:1.0"},
                    {"name": "migrate", "image": "other:1.0"},
                ],
            )

    def test_accepts_environment_and_mounts(self) -> None:
        application = _containers_application(
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

        init_container = application.spec.init_containers[0]
        self.assertEqual(init_container.environment[0].name, "DATABASE_URL")
        self.assertEqual(init_container.mounts[0].storage, "data")
