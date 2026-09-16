import unittest

from pydantic import ValidationError

from kubeapp.models import Application, DataResource
from .helpers import _container, _containers_application


class DataResourceModelTests(unittest.TestCase):
    def test_local_names_and_data_keys_have_distinct_rules(self):
        for key in ("dotted.key", "under_score", "MixedCase", "with-dash"):
            with self.subTest(key=key):
                self.assertEqual(DataResource(name="settings", data={key: "ok"}).data, {key: "ok"})
        for name in ("dotted.name", "under_score", "MixedCase", "with space"):
            with self.subTest(name=name), self.assertRaises(ValidationError):
                DataResource(name=name, data={})
        for key in ("", "with space"):
            with self.subTest(key=key), self.assertRaises(ValidationError):
                DataResource(name="settings", data={key: "value"})

    def test_duplicate_secret_names_are_rejected(self):
        with self.assertRaisesRegex(ValidationError, "duplicate resource name"):
            Application.model_validate({
                "name": "worker",
                "containers": [{"name": "worker", "image": "worker:1"}],
                "secrets": [
                    {"name": "credentials", "data": {"KEY": "one"}},
                    {"name": "credentials", "data": {"KEY": "two"}},
                ],
            })

    def test_empty_data_is_a_valid_source(self):
        resource = DataResource(name="settings", data={})
        self.assertEqual(resource.data, {})
        self.assertIsNone(resource.file)


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
                {"name": "RATIO", "value": 0.5},
                {"name": "DISABLED", "value": False},
            ],
        )

        self.assertEqual(container.environment[0].value, "8")
        self.assertEqual(container.environment[1].value, "true")
        self.assertEqual(container.environment[2].value, "0.5")
        self.assertEqual(container.environment[3].value, "false")

    def test_accepts_dotted_provider_name(self):
        container = _container(environment=[{
            "name": "Mixed_CASE", "config": {"name": "settings.example", "key": "Mixed.key_name"},
        }])
        self.assertEqual(container.environment[0].config.name, "settings.example")
        self.assertEqual(container.environment[0].config.key, "Mixed.key_name")

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
                        environment=[{"name": "DATABASE_URL", "secret": secret}],
                    )
