import copy
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml
from pydantic import ValidationError

from kubeapp.manifests import application_to_kubernetes_manifests
from kubeapp.models import Application
from kubeapp.parser import load_application

from .helpers import PROJECT_ROOT as ROOT, _container, _pod_spec


class IntentTests(unittest.TestCase):
    def test_scalar_values_render_as_strings(self):
        values = {"BOOL": True, "FALSE": False, "INT": 3, "FLOAT": 0.5, "STRING": "003"}
        expected = {"BOOL": "true", "FALSE": "false", "INT": "3", "FLOAT": "0.5", "STRING": "003"}
        manifests = self.render({
            "name": "worker",
            "containers": [{"name": "worker", "image": "worker:1", "environment": values}],
            "configuration": [{"name": "settings", "data": values}],
            "secrets": [{"name": "credentials", "data": values}],
        })
        self.assertEqual(next(m for m in manifests if m["kind"] == "ConfigMap")["data"], expected)
        secret = next(m for m in manifests if m["kind"] == "Secret")
        self.assertEqual(secret["stringData"], expected)
        self.assertEqual(secret["type"], "Opaque")
        self.assertEqual(_container(manifests)["env"], [
            {"name": key, "value": value} for key, value in expected.items()
        ])

    def test_fractional_cpu_and_equal_resource_bounds(self):
        manifests = self.render({
            "name": "worker", "containers": [{
                "name": "worker", "image": "worker:1",
                "resources": {"cpu": {"min": 0.5, "max": 0.5}},
            }],
        })
        self.assertEqual(_container(manifests)["resources"], {
            "requests": {"cpu": "0.5"}, "limits": {"cpu": "0.5"},
        })

    def test_different_applications_name_their_own_claims(self):
        names = []
        for name in ("catalog", "worker"):
            data = copy.deepcopy(self.data)
            data["name"] = name
            manifests = self.render(data)
            claim = next(m for m in manifests if m["kind"] == "PersistentVolumeClaim")
            names.append(claim["metadata"]["name"])
            volume = next(v for v in _pod_spec(manifests)["volumes"] if "persistentVolumeClaim" in v)
            self.assertEqual(volume["persistentVolumeClaim"]["claimName"], names[-1])
        self.assertEqual(names, ["catalog-data", "worker-data"])

    def test_read_only_access_mode_does_not_change_mount_flag(self):
        self.data["storage"]["accessModes"] = ["ReadOnlyMany"]
        manifests = self.render()
        claim = next(m for m in manifests if m["kind"] == "PersistentVolumeClaim")
        self.assertEqual(claim["spec"]["accessModes"], ["ReadOnlyMany"])
        mount = next(m for m in _container(manifests)["volumeMounts"] if m["mountPath"] == "/data")
        self.assertNotIn("readOnly", mount)

    def setUp(self):
        self.data = yaml.safe_load((ROOT / "examples/medium/app.yaml").read_text())

    def render(self, data=None):
        return application_to_kubernetes_manifests(
            Application.model_validate(data or self.data)
        )

    def test_medium_output_and_resource_wiring(self):
        manifests = self.render()
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
            lambda d: d.pop("storage"),
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
                "# comment\n  ! another comment\n\n  KEY = ${TEST_CONFIG}  \nEMPTY=\nURL=a=b\n"
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
