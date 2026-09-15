"""Basic Helm values and explicit capability limits."""

import unittest
import os
from pathlib import Path
from typing import Any
from unittest.mock import patch

from kubeapp.models import Application
from kubeapp.parser import load_application
from kubeapp.renderers import HelmRenderer, Renderer

from .helpers import inline_secret_application

ROOT = Path(__file__).resolve().parents[2]


class HelmRendererTests(unittest.TestCase):
    def test_inline_secret_values_substitution_and_consumption_order(self):
        application = inline_secret_application()
        before = application.model_dump()
        with patch.dict(os.environ, {"HELM_TEST_PASSWORD": "example"}):
            values = HelmRenderer().render(application)
            self.assertEqual(HelmRenderer().render(application), values)
        self.assertEqual(values["secrets"], [
            {"name": "z-db", "data": {
                "PASSWORD": "prefix-example", "PORT": "5432", "ENABLED": "false",
                "MULTILINE": "first\nsecond\n", "LITERAL": "{{ .Release.Name }}", "EMPTY": "",
            }},
            {"name": "a-api", "data": {"TOKEN": "demonstration-token"}},
            {"name": "unused-secret", "data": {}},
        ])
        self.assertEqual(values["envFrom"], [
            {"configMapRef": {"name": "catalog-config"}},
            {"secretRef": {"name": "a-api"}},
            {"secretRef": {"name": "z-db"}},
        ])
        self.assertEqual(application.model_dump(), before)
        application.containers[0].configuration = []
        application.containers[0].secrets = []
        with patch.dict(os.environ, {"HELM_TEST_PASSWORD": "example"}):
            unconsumed = HelmRenderer().render(application)
        self.assertEqual(unconsumed["secrets"], values["secrets"])
        self.assertNotIn("envFrom", unconsumed)

    def test_missing_secret_substitution_fails_without_exposing_data(self):
        application = inline_secret_application()
        before = application.model_dump()
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError) as raised:
                HelmRenderer().render(application)
        self.assertEqual(
            str(raised.exception),
            "Missing environment variable 'HELM_TEST_PASSWORD' for resource 'z-db'",
        )
        self.assertNotIn("demonstration-token", str(raised.exception))
        self.assertEqual(application.model_dump(), before)

    def test_inline_configuration_values_and_environment_references(self):
        application = Application.model_validate({
            "name": "catalog",
            "configuration": [
                {"name": "catalog-config", "data": {
                    "APP_ENV": "production", "COUNT": 3, "ENABLED": True,
                    "MESSAGE": "hello ${CONFIG_TEST_USER}",
                }},
                {"name": "unused-config", "data": {}},
            ],
            "containers": [{
                "name": "catalog", "image": "catalog:1.4.2",
                "configuration": [{"name": "catalog-config", "as": "environment"}],
            }],
        })
        before = application.model_dump()
        with patch.dict(os.environ, {"CONFIG_TEST_USER": "reader"}):
            values = HelmRenderer().render(application)
        self.assertEqual(values["configuration"], [
            {"name": "catalog-config", "data": {
                "APP_ENV": "production", "COUNT": "3", "ENABLED": "true",
                "MESSAGE": "hello reader",
            }},
            {"name": "unused-config", "data": {}},
        ])
        self.assertEqual(values["envFrom"], [{"configMapRef": {"name": "catalog-config"}}])
        self.assertEqual(application.model_dump(), before)
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "Missing environment variable 'CONFIG_TEST_USER'"):
                HelmRenderer().render(application)

    def test_inline_resources_do_not_enable_files_or_mounts(self):
        base = {
            "name": "catalog",
            "configuration": [{"name": "config", "data": {}}],
            "containers": [{"name": "catalog", "image": "catalog:1"}],
        }
        for capability in ("file", "mounts", "secrets"):
            with self.subTest(capability=capability):
                application = Application.model_validate(base)
                data = application.model_dump(by_alias=True, exclude_none=True)
                if capability == "file":
                    data["configuration"] = [{"name": "config", "file": "missing.env"}]
                elif capability == "mounts":
                    data["containers"][0]["mounts"] = [{"configuration": "config", "path": "/etc/app"}]
                else:
                    data["secrets"] = [{"name": "private", "file": "missing-secret.env"}]
                with self.assertRaisesRegex(NotImplementedError, capability):
                    HelmRenderer().render(Application.model_validate(data))

    def test_basic_values_contract_and_immutability(self):
        renderer: Renderer[dict[str, Any]] = HelmRenderer()
        application = load_application(ROOT / "examples/basic/app.yaml")
        before = application.model_dump()
        expected = {
            "name": "hello-world",
            "replicaCount": 2,
            "containerName": "hello-world",
            "image": {
                "repository": "nginxinc/nginx-unprivileged",
                "tag": "1.27", "pullPolicy": "IfNotPresent",
            },
            "ports": [{"name": "http", "containerPort": 8080, "protocol": "TCP"}],
            "resources": {
                "requests": {"cpu": "100m", "memory": "128Mi"},
                "limits": {"cpu": "500m", "memory": "256Mi"},
            },
            "service": {
                "enabled": True, "type": "ClusterIP", "port": 80, "targetPort": "http",
            },
            "serviceAccount": {"create": False},
        }
        for options in ({}, {"base_dir": "."}, {"base_dir": Path(".")}):
            with self.subTest(options=options):
                self.assertEqual(renderer.render(application, **options), expected)
                self.assertEqual(application.model_dump(), before)

    def test_basic_variations_and_optional_resources(self):
        for image, tag in (("registry.local:5000/app", "latest"),
                           ("registry.local:5000/app:2", "2")):
            with self.subTest(image=image):
                application = Application.model_validate({
                    "name": "worker", "replicas": 0,
                    "containers": [{
                        "name": "process", "image": image,
                        "imagePullPolicy": "Always",
                        "resources": {"cpu": {"max": "500m"}},
                    }],
                })
                values = HelmRenderer().render(application)
                self.assertEqual(values["image"], {
                    "repository": "registry.local:5000/app", "tag": tag,
                    "pullPolicy": "Always",
                })
                self.assertEqual(values["replicaCount"], 0)
                self.assertEqual(values["containerName"], "process")
                self.assertEqual(values["resources"], {"limits": {"cpu": "500m"}})
                self.assertEqual(values["service"], {"enabled": False})
                self.assertEqual(values["ports"], [])
                application.containers[0].resources = None
                self.assertEqual(HelmRenderer().render(application)["resources"], {})

    def test_medium_and_advanced_fail_without_partial_output(self):
        for example in ("medium", "advanced"):
            with self.subTest(example=example):
                application = load_application(ROOT / f"examples/{example}/app.yaml")
                before = application.model_dump()
                with self.assertRaisesRegex(NotImplementedError, "only Basic capabilities"):
                    HelmRenderer().render(application)
                self.assertEqual(application.model_dump(), before)

    def test_unsupported_capabilities_are_not_silently_dropped(self):
        for field, value in (
            ("environment", {"MODE": "test"}),
            ("command", ["run"]),
            ("args", ["--debug"]),
            ("health", {"readiness": {"path": "/", "port": 8080}}),
            ("ports", [{"name": "dns", "port": 5353, "protocol": "UDP"}]),
            ("image", "nginx@sha256:abcd"),
        ):
            with self.subTest(field=field):
                application = Application.model_validate({
                    "name": "worker",
                    "containers": [{"name": "worker", "image": "nginx", field: value}],
                })
                with self.assertRaisesRegex(NotImplementedError, field):
                    HelmRenderer().render(application)
