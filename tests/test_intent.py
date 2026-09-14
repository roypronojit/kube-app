import copy
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

import yaml
from pydantic import ValidationError

from kubeapp.cli import main
from kubeapp.manifests import application_to_kubernetes_manifests
from kubeapp.models import Application
from kubeapp.parser import load_application

ROOT = Path(__file__).resolve().parents[1]


class IntentTests(unittest.TestCase):
    def setUp(self):
        self.data = yaml.safe_load((ROOT / "examples/medium/app.yaml").read_text())

    def render(self, data=None):
        return application_to_kubernetes_manifests(
            Application.model_validate(data or self.data)
        )

    def test_medium_output_and_resource_wiring(self):
        manifests = self.render()
        self.assertEqual(
            manifests,
            list(
                yaml.safe_load_all((ROOT / "examples/medium/rendered.yaml").read_text())
            ),
        )
        config, secret, claim, deployment, service = manifests
        self.assertEqual(config["data"], {"APP_ENV": "production", "LOG_LEVEL": "info"})
        self.assertEqual(secret["stringData"]["DB_PORT"], "5432")
        self.assertEqual(claim["spec"]["resources"]["requests"]["storage"], "10Gi")
        self.assertEqual(deployment["spec"]["replicas"], 3)
        pod = deployment["spec"]["template"]["spec"]
        container = pod["containers"][0]
        self.assertEqual(
            container["envFrom"],
            [
                {"configMapRef": {"name": "catalog-config"}},
                {"secretRef": {"name": "catalog-db"}},
            ],
        )
        self.assertEqual(
            container["resources"],
            {
                "requests": {"cpu": "250m", "memory": "256Mi"},
                "limits": {"cpu": "1", "memory": "512Mi"},
            },
        )
        self.assertEqual(service["spec"]["type"], "LoadBalancer")
        self.assertEqual(
            service["spec"]["selector"], deployment["spec"]["selector"]["matchLabels"]
        )
        self.assertEqual(len(pod["volumes"]), 3)
        self.assertEqual(
            [m["mountPath"] for m in container["volumeMounts"]],
            ["/etc/catalog", "/etc/catalog/secrets", "/data"],
        )

    def test_all_checked_in_examples_match_renderer(self):
        with patch.dict(os.environ, {"CATALOG_API_KEY": "example-api-key"}):
            for name in ("basic", "medium", "advanced"):
                with self.subTest(example=name):
                    base = ROOT / "examples" / name
                    manifests = application_to_kubernetes_manifests(
                        load_application(base / "app.yaml"), base
                    )
                    self.assertEqual(
                        manifests,
                        list(yaml.safe_load_all((base / "rendered.yaml").read_text())),
                    )
                    pod = next(m for m in manifests if m["kind"] == "Deployment")[
                        "spec"
                    ]["template"]["spec"]
                    self.assertNotIn("securityContext", pod)
                    for container in pod["containers"] + pod.get("initContainers", []):
                        self.assertNotIn("securityContext", container)

    def test_defaults_and_zero_replicas(self):
        data = {
            "name": "worker",
            "containers": [{"name": "worker", "image": "worker:1"}],
        }
        self.assertEqual(self.render(data)[0]["spec"]["replicas"], 1)
        data["replicas"] = 0
        self.assertEqual(self.render(data)[0]["spec"]["replicas"], 0)

    def test_invalid_intent(self):
        mutations = [
            lambda d: d.update(replicas=-1),
            lambda d: d.update(replicas=True),
            lambda d: d.update(spec={}),
            lambda d: d.update(containers=[]),
            lambda d: d["configuration"][0].update(file="also.properties"),
            lambda d: d["configuration"][0].pop("data"),
            lambda d: d["configuration"].append(copy.deepcopy(d["configuration"][0])),
            lambda d: d["containers"][0]["configuration"][0].update(name="missing"),
            lambda d: d["containers"][0]["secrets"][0].update(name="missing"),
            lambda d: d["containers"][0]["mounts"][2].update(storage="missing"),
            lambda d: d["containers"][0]["mounts"][0].update(secret="catalog-db"),
            lambda d: d["containers"][0]["mounts"][0].update(path="relative"),
            lambda d: d["containers"][0]["configuration"][0].update({"as": "files"}),
            lambda d: d["containers"][0]["resources"]["cpu"].update(min="2", max="1"),
            lambda d: d["containers"][0]["resources"]["cpu"].update(min="invalid"),
            lambda d: d.update(init=[copy.deepcopy(d["containers"][0])]),
            lambda d: d["service"].update(container="missing"),
            lambda d: d["containers"].append({"name": "metrics", "image": "metrics:1"}),
        ]
        for mutation in mutations:
            data = copy.deepcopy(self.data)
            mutation(data)
            with self.subTest(data=data), self.assertRaises(ValidationError):
                Application.model_validate(data)

    def test_volume_sources_with_same_name_do_not_collide(self):
        self.data["secrets"][0]["name"] = "catalog-config"
        self.data["containers"][0]["secrets"][0]["name"] = "catalog-config"
        self.data["containers"][0]["mounts"][1]["secret"] = "catalog-config"
        self.data["init"] = [
            {
                "name": "init",
                "image": "init:1",
                "mounts": [{"storage": "data", "path": "/init"}],
            }
        ]
        pod = self.render()[-2]["spec"]["template"]["spec"]
        self.assertEqual(len({v["name"] for v in pod["volumes"]}), 3)
        self.assertEqual(
            pod["initContainers"][0]["volumeMounts"][0]["name"],
            pod["containers"][0]["volumeMounts"][2]["name"],
        )

    def test_files_read_at_render_time_and_interpolation(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            self.data["configuration"][0] = {
                "name": "catalog-config",
                "file": "config.properties",
            }
            (base / "app.yaml").write_text(yaml.safe_dump(self.data))
            app = load_application(base / "app.yaml")
            with self.assertRaisesRegex(ValueError, "Cannot read resource file"):
                application_to_kubernetes_manifests(app, base)
            (base / "config.properties").write_text(
                "# comment\nKEY=${TEST_CONFIG}\nEMPTY=\nURL=a=b\n"
            )
            with patch.dict(os.environ, {"TEST_CONFIG": "resolved"}):
                result = application_to_kubernetes_manifests(app, base)
            self.assertEqual(
                result[0]["data"], {"KEY": "resolved", "EMPTY": "", "URL": "a=b"}
            )
            with (
                patch.dict(os.environ, {}, clear=True),
                self.assertRaisesRegex(ValueError, "Missing environment variable"),
            ):
                application_to_kubernetes_manifests(app, base)
            for content in ("bad entry", "KEY=a\nKEY=b", "bad key=value"):
                (base / "config.properties").write_text(content)
                with self.assertRaisesRegex(ValueError, "Invalid or duplicate"):
                    application_to_kubernetes_manifests(app, base)

    def test_failed_render_preserves_output_and_hides_secret_values(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            self.data["secrets"][0]["data"]["DB_PASSWORD"] = {
                "invalid": "private-value"
            }
            source, output = base / "app.yaml", base / "output.yaml"
            source.write_text(yaml.safe_dump(self.data))
            output.write_text("existing")
            errors = io.StringIO()
            with (
                patch.object(
                    sys, "argv", ["kube-app", "render", str(source), "-o", str(output)]
                ),
                redirect_stderr(errors),
            ):
                self.assertEqual(main(), 1)
            self.assertNotIn("private-value", errors.getvalue())
            self.assertEqual(output.read_text(), "existing")
