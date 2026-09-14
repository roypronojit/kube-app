import unittest

from pydantic import ValidationError

from .helpers import _container, _containers_application, _storage_application


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
                    "mounts": [{"name": "data", "storage": "data", "path": "/data"}],
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
