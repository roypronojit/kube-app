import unittest
from pathlib import Path

import yaml
from pydantic import ValidationError

from kubeapp.models import Application as IntentApplication
from kubeapp.models import LegacyApplication as Application

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ApplicationModelTests(unittest.TestCase):
    def test_accepts_basic_example(self) -> None:
        application = _example("basic/app.yaml")

        self.assertEqual(application.name, "hello-world")
        self.assertEqual(application.containers[0].image, "nginx:1.27")
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
                initContainers=[
                    {"name": "hello-world", "image": "migrate:1.0"}
                ],
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


class EnvironmentModelTests(unittest.TestCase):
    def test_accepts_literal_value(self) -> None:
        container = _container(
            environment=[{"name": "APP_ENV", "value": "production"}],
        )

        self.assertEqual(container.environment[0].value, "production")

    def test_accepts_numbers_and_booleans(self) -> None:
        container = _container(
            environment=[
                {"name": "MAX_THREADS", "value": 8},
                {"name": "FEATURE_SEARCH", "value": True},
            ],
        )

        self.assertEqual(container.environment[0].value, "8")
        self.assertEqual(container.environment[1].value, "true")

    def test_accepts_secret_source(self) -> None:
        container = _container(
            environment=[
                {
                    "name": "DATABASE_URL",
                    "secret": {"name": "catalog-db", "key": "url"},
                }
            ],
        )

        self.assertEqual(container.environment[0].secret.name, "catalog-db")
        self.assertEqual(container.environment[0].secret.key, "url")

    def test_accepts_config_source(self) -> None:
        container = _container(
            environment=[
                {
                    "name": "APP_CONFIG",
                    "config": {"name": "catalog-config", "key": "config"},
                }
            ],
        )

        self.assertEqual(
            container.environment[0].config.name,
            "catalog-config",
        )

    def test_rejects_ambiguous_source(self) -> None:
        ambiguous = [
            {
                "name": "DATABASE_URL",
                "value": "postgres://localhost",
                "secret": {"name": "catalog-db", "key": "url"},
            },
            {
                "name": "APP_CONFIG",
                "secret": {"name": "catalog-db", "key": "url"},
                "config": {"name": "catalog-config", "key": "config"},
            },
        ]

        for variable in ambiguous:
            with self.subTest(variable=variable):
                with self.assertRaises(ValidationError):
                    _container(environment=[variable])

    def test_rejects_missing_source(self) -> None:
        with self.assertRaises(ValidationError):
            _container(environment=[{"name": "APP_ENV"}])

    def test_rejects_duplicate_environment_names(self) -> None:
        with self.assertRaises(ValidationError):
            _container(
                environment=[
                    {"name": "APP_ENV", "value": "production"},
                    {"name": "APP_ENV", "value": "staging"},
                ],
            )

    def test_allows_the_same_name_in_different_containers(self) -> None:
        application = _containers_application(
            containers=[
                {
                    "name": "app",
                    "image": "app:1.0",
                    "environment": [{"name": "LOG_LEVEL", "value": "info"}],
                },
                {
                    "name": "sidecar",
                    "image": "sidecar:1.0",
                    "environment": [{"name": "LOG_LEVEL", "value": "debug"}],
                },
            ],
            service={"port": 8080, "container": "app"},
        )

        self.assertEqual(len(application.spec.containers), 2)

    def test_rejects_invalid_environment_names(self) -> None:
        for name in ["", "1_APP", "APP-ENV", "APP ENV"]:
            with self.subTest(name=name):
                with self.assertRaises(ValidationError):
                    _container(environment=[{"name": name, "value": "x"}])

    def test_rejects_invalid_provider_reference(self) -> None:
        invalid = [
            {"name": "Catalog_DB", "key": "url"},
            {"name": "catalog-db", "key": "the url"},
            {"name": "catalog-db"},
            {"key": "url"},
        ]

        for secret in invalid:
            with self.subTest(secret=secret):
                with self.assertRaises(ValidationError):
                    _container(
                        environment=[
                            {"name": "DATABASE_URL", "secret": secret}
                        ],
                    )


class MountModelTests(unittest.TestCase):
    def test_accepts_config_mount(self) -> None:
        container = _container(
            mounts=[
                {
                    "name": "catalog-config",
                    "config": {"name": "catalog-config"},
                    "path": "/etc/catalog",
                }
            ],
        )

        self.assertEqual(container.mounts[0].config.name, "catalog-config")
        self.assertEqual(container.mounts[0].source, ("config", "catalog-config"))

    def test_accepts_secret_mount(self) -> None:
        container = _container(
            mounts=[
                {
                    "name": "catalog-tls",
                    "secret": {"name": "catalog-tls"},
                    "path": "/etc/catalog/tls",
                }
            ],
        )

        self.assertEqual(container.mounts[0].secret.name, "catalog-tls")

    def test_accepts_storage_mount(self) -> None:
        application = _containers_application(
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
            application.spec.containers[0].mounts[0].storage,
            "data",
        )

    def test_rejects_ambiguous_mount(self) -> None:
        with self.assertRaises(ValidationError):
            _container(
                mounts=[
                    {
                        "name": "catalog-config",
                        "config": {"name": "catalog-config"},
                        "secret": {"name": "catalog-tls"},
                        "path": "/etc/catalog",
                    }
                ],
            )

    def test_rejects_mount_without_source(self) -> None:
        with self.assertRaises(ValidationError):
            _container(
                mounts=[{"name": "catalog-config", "path": "/etc/catalog"}],
            )

    def test_rejects_mount_without_path(self) -> None:
        with self.assertRaises(ValidationError):
            _container(
                mounts=[
                    {
                        "name": "catalog-config",
                        "config": {"name": "catalog-config"},
                    }
                ],
            )

    def test_rejects_relative_mount_path(self) -> None:
        for path in ["", "etc/catalog", "./etc"]:
            with self.subTest(path=path):
                with self.assertRaises(ValidationError):
                    _container(
                        mounts=[
                            {
                                "name": "catalog-config",
                                "config": {"name": "catalog-config"},
                                "path": path,
                            }
                        ],
                    )

    def test_rejects_duplicate_mount_names_in_a_container(self) -> None:
        with self.assertRaises(ValidationError):
            _container(
                mounts=[
                    {
                        "name": "catalog-config",
                        "config": {"name": "catalog-config"},
                        "path": "/etc/catalog",
                    },
                    {
                        "name": "catalog-config",
                        "config": {"name": "catalog-config"},
                        "path": "/etc/other",
                    },
                ],
            )

    def test_rejects_duplicate_mount_paths_in_a_container(self) -> None:
        with self.assertRaises(ValidationError):
            _container(
                mounts=[
                    {
                        "name": "catalog-config",
                        "config": {"name": "catalog-config"},
                        "path": "/etc/catalog",
                    },
                    {
                        "name": "catalog-tls",
                        "secret": {"name": "catalog-tls"},
                        "path": "/etc/catalog",
                    },
                ],
            )

    def test_allows_the_same_mount_in_two_containers(self) -> None:
        application = _containers_application(
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

        self.assertEqual(len(application.spec.containers), 2)

    def test_rejects_the_same_mount_name_for_different_sources(self) -> None:
        with self.assertRaises(ValidationError):
            _containers_application(
                containers=[
                    {
                        "name": "app",
                        "image": "app:1.0",
                        "mounts": [
                            {
                                "name": "shared",
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
                                "name": "shared",
                                "secret": {"name": "catalog-tls"},
                                "path": "/etc/tls",
                            }
                        ],
                    },
                ],
                service={"port": 8080, "container": "app"},
            )

    def test_rejects_reference_to_undefined_storage(self) -> None:
        with self.assertRaises(ValidationError):
            _containers_application(
                containers=[
                    {
                        "name": "app",
                        "image": "app:1.0",
                        "mounts": [
                            {
                                "name": "data",
                                "storage": "missing",
                                "path": "/data",
                            }
                        ],
                    }
                ],
                storage=[{"name": "data", "size": "10Gi"}],
            )


class StorageModelTests(unittest.TestCase):
    def test_accepts_storage(self) -> None:
        application = _storage_application(
            [{"name": "data", "size": "10Gi", "storageClass": "fast"}],
        )

        storage = application.spec.storage[0]
        self.assertEqual(storage.size, "10Gi")
        self.assertEqual(storage.storage_class, "fast")

    def test_defaults_access_modes(self) -> None:
        application = _storage_application(
            [{"name": "data", "size": "10Gi"}],
        )

        self.assertEqual(
            application.spec.storage[0].access_modes,
            ["ReadWriteOnce"],
        )
        self.assertIsNone(application.spec.storage[0].storage_class)

    def test_accepts_explicit_access_modes(self) -> None:
        application = _storage_application(
            [
                {
                    "name": "data",
                    "size": "10Gi",
                    "accessModes": ["ReadWriteMany", "ReadOnlyMany"],
                }
            ],
        )

        self.assertEqual(
            application.spec.storage[0].access_modes,
            ["ReadWriteMany", "ReadOnlyMany"],
        )

    def test_accepts_multiple_storage_definitions(self) -> None:
        application = _containers_application(
            containers=[
                {
                    "name": "app",
                    "image": "app:1.0",
                    "mounts": [
                        {"name": "data", "storage": "data", "path": "/data"},
                        {
                            "name": "cache",
                            "storage": "cache",
                            "path": "/cache",
                        },
                    ],
                }
            ],
            storage=[
                {"name": "data", "size": "10Gi"},
                {"name": "cache", "size": "1Gi"},
            ],
        )

        self.assertEqual(
            [storage.name for storage in application.spec.storage],
            ["data", "cache"],
        )

    def test_rejects_invalid_access_mode(self) -> None:
        with self.assertRaises(ValidationError):
            _storage_application(
                [
                    {
                        "name": "data",
                        "size": "10Gi",
                        "accessModes": ["ReadWriteEverywhere"],
                    }
                ],
            )

    def test_rejects_empty_access_modes(self) -> None:
        with self.assertRaises(ValidationError):
            _storage_application(
                [{"name": "data", "size": "10Gi", "accessModes": []}],
            )

    def test_rejects_invalid_storage_names(self) -> None:
        for name in ["", "Data", "app_data", "-data"]:
            with self.subTest(name=name):
                with self.assertRaises(ValidationError):
                    _containers_application(
                        containers=[
                            {
                                "name": "app",
                                "image": "app:1.0",
                                "mounts": [
                                    {
                                        "name": "data",
                                        "storage": name,
                                        "path": "/data",
                                    }
                                ],
                            }
                        ],
                        storage=[{"name": name, "size": "10Gi"}],
                    )

    def test_rejects_duplicate_storage_names(self) -> None:
        with self.assertRaises(ValidationError):
            _storage_application(
                [
                    {"name": "data", "size": "10Gi"},
                    {"name": "data", "size": "20Gi"},
                ],
            )

    def test_rejects_invalid_storage_sizes(self) -> None:
        for size in ["", "10 Gi", "ten", "10GB", "-5Gi", "10gi"]:
            with self.subTest(size=size):
                with self.assertRaises(ValidationError):
                    _storage_application(
                        [{"name": "data", "size": size}],
                    )

    def test_rejects_zero_storage_size(self) -> None:
        with self.assertRaises(ValidationError):
            _storage_application([{"name": "data", "size": "0Gi"}])

    def test_rejects_invalid_storage_class(self) -> None:
        with self.assertRaises(ValidationError):
            _storage_application(
                [{"name": "data", "size": "10Gi", "storageClass": "Fast_SSD"}],
            )

    def test_rejects_storage_that_is_never_mounted(self) -> None:
        with self.assertRaises(ValidationError):
            _containers_application(
                containers=[{"name": "app", "image": "app:1.0"}],
                storage=[{"name": "data", "size": "10Gi"}],
            )

    def test_rejects_kubernetes_storage_fields(self) -> None:
        rejected = [
            {"name": "data", "size": "10Gi", "claimName": "catalog-data"},
            {"name": "data", "size": "10Gi", "mountPath": "/data"},
            {
                "name": "data",
                "size": "10Gi",
                "persistentVolumeClaim": {"claimName": "x"},
            },
        ]

        for storage in rejected:
            with self.subTest(storage=storage):
                with self.assertRaises(ValidationError):
                    _storage_application([storage])


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

        init_container = application.spec.init_containers[0]
        self.assertEqual(init_container.environment[0].name, "DATABASE_URL")
        self.assertEqual(init_container.mounts[0].storage, "data")


def _example(name: str) -> Application:
    return IntentApplication.model_validate(
        yaml.safe_load(
            (PROJECT_ROOT / "examples" / name).read_text(encoding="utf-8")
        )
    )


def _application_data(name: str = "hello-world") -> dict[str, object]:
    return {
        "apiVersion": "kubeapp.dev/v1alpha1",
        "kind": "Application",
        "metadata": {"name": name},
        "spec": {"image": "nginx:1.27"},
    }


def _application(**spec_fields: object) -> Application:
    application_data = _application_data()
    application_data["spec"].update(spec_fields)

    return Application.model_validate(application_data)


def _containers_application(**spec_fields: object) -> Application:
    application_data = _application_data()
    application_data["spec"] = dict(spec_fields)

    return Application.model_validate(application_data)


def _container(**container_fields: object):
    container = {"name": "app", "image": "app:1.0"}
    container.update(container_fields)
    application = _containers_application(containers=[container])

    return application.spec.containers[0]


def _storage_application(storage: list[dict[str, object]]) -> Application:
    mounts = [
        {
            "name": entry["name"],
            "storage": entry["name"],
            "path": f"/{entry['name']}",
        }
        for entry in storage
    ]

    return _containers_application(
        containers=[
            {"name": "app", "image": "app:1.0", "mounts": mounts},
        ],
        storage=storage,
    )
