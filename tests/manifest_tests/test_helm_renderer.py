"""Basic Helm values and explicit capability limits."""

import unittest
from pathlib import Path
from typing import Any

from kubeapp.models import Application
from kubeapp.parser import load_application
from kubeapp.renderers import HelmRenderer, Renderer

ROOT = Path(__file__).resolve().parents[2]


class HelmRendererTests(unittest.TestCase):
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
