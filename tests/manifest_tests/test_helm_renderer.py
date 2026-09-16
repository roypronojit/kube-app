"""Basic Helm values and explicit capability limits."""

import unittest
import os
from pathlib import Path
from typing import Any
from unittest.mock import patch

from kubeapp.models import Application
from kubeapp.parser import load_application
from kubeapp.renderers import HelmRenderer, Renderer

from .helpers import health_application, inline_secret_application, mounted_application, multiple_container_application
from .helpers import init_container_application
from .helpers import process_application

ROOT = Path(__file__).resolve().parents[2]


class HelmRendererTests(unittest.TestCase):
    def test_service_account_values_exact_name_and_immutability(self):
        for name in (None, "catalog.identity", "true"):
            with self.subTest(name=name):
                data = init_container_application().model_dump(by_alias=True)
                data["serviceAccount"] = name
                application = Application.model_validate(data)
                before = application.model_dump()
                values = HelmRenderer().render(application)
                expected = {"create": False}
                if name is not None:
                    expected["name"] = name
                self.assertEqual(values["serviceAccount"], expected)
                self.assertEqual(application.model_dump(), before)

    def test_init_container_values_and_shared_volumes(self):
        for count in (1, 2):
            with self.subTest(count=count):
                application = init_container_application(count)
                before = application.model_dump()
                values = HelmRenderer().render(application)
                init = values["initContainers"]
                self.assertEqual([c["containerName"] for c in init], ["prepare", "verify"][:count])
                self.assertEqual(init[0]["image"], {"repository": "prepare", "tag": "1", "pullPolicy": "Always"})
                self.assertEqual(init[0]["env"], [{"name": "TASK", "value": "prepare"}])
                self.assertEqual(init[0]["envFrom"], [{"configMapRef": {"name": "data"}}, {"secretRef": {"name": "data"}}])
                self.assertEqual(init[0]["resources"], {"requests": {"cpu": "50m"}})
                self.assertEqual(init[0]["volumeMounts"][0], {"name": "volume-0", "mountPath": "/init/data"})
                self.assertEqual(len(values["volumes"]), 3)
                self.assertEqual(values["volumes"][0], {"name": "volume-0", "persistentVolumeClaim": {"claimName": "catalog-data"}})
                for container in init:
                    self.assertNotIn("ports", container)
                    self.assertFalse(any(key.endswith("Probe") for key in container))
                self.assertEqual(application.model_dump(), before)

    def test_command_args_values_preserve_order_and_do_not_alias_model(self):
        application = process_application()
        before = application.model_dump()
        values = HelmRenderer().render(application)
        for field, models in (("containers", application.containers), ("initContainers", application.init)):
            for rendered, model in zip(values[field], models):
                with self.subTest(container=model.name):
                    self.assertEqual(rendered["containerName"], model.name)
                    for key in ("command", "args"):
                        expected = getattr(model, key)
                        if expected is None:
                            self.assertNotIn(key, rendered)
                        else:
                            self.assertEqual(rendered[key], expected)
                            self.assertIsNot(rendered[key], expected)
                            rendered[key].append("output-only")
        self.assertEqual(application.model_dump(), before)

    def test_multiple_containers_keep_independent_values_and_shared_resources(self):
        application = multiple_container_application()
        before = application.model_dump()
        values = HelmRenderer().render(application)
        containers = values["containers"]
        self.assertEqual([c["containerName"] for c in containers], ["catalog", "metrics", "worker"])
        self.assertEqual([c["image"]["pullPolicy"] for c in containers], ["IfNotPresent", "Always", "Never"])
        self.assertEqual(containers[1]["image"], {"repository": "registry.local/metrics", "tag": "2", "pullPolicy": "Always"})
        self.assertEqual(containers[0]["env"], [{"name": "ROLE", "value": "primary"}])
        self.assertEqual(containers[1]["env"], [{"name": "ROLE", "value": "metrics"}])
        self.assertNotIn("env", containers[2])
        self.assertNotIn("volumeMounts", containers[2])
        self.assertNotIn("livenessProbe", containers[0])
        self.assertNotIn("readinessProbe", containers[1])
        self.assertEqual(len(values["configuration"]), 1)
        self.assertEqual(len(values["secrets"]), 1)
        self.assertEqual(len(values["volumes"]), 3)
        self.assertEqual(containers[1]["volumeMounts"][0], {"name": "volume-1", "mountPath": "/metrics/data"})
        self.assertEqual(values["storage"]["name"], "data")
        self.assertEqual(application.model_dump(), before)
        self.assertEqual(HelmRenderer().render(application), values)

    def test_service_selection_uses_selected_container_ports(self):
        for target in (None, "metrics", 9090):
            with self.subTest(target=target):
                data = multiple_container_application().model_dump(by_alias=True)
                data["service"] = {"port": 80, "container": "metrics", "targetPort": target}
                application = Application.model_validate(data)
                before = application.model_dump()
                values = HelmRenderer().render(application)
                self.assertEqual(values["service"]["targetPort"], target or "metrics")
                self.assertEqual(application.model_dump(), before)

    def test_service_selection_checks_selected_container_not_first(self):
        for first_has_ports in (False, True):
            for selected in ("metrics", "worker"):
                with self.subTest(first_has_ports=first_has_ports, selected=selected):
                    data = multiple_container_application().model_dump(by_alias=True)
                    if not first_has_ports:
                        data["containers"][0]["ports"] = []
                        data["containers"][0]["health"] = None
                    data["service"] = {"port": 80, "container": selected}
                    application = Application.model_validate(data)
                    self.assertEqual(
                        HelmRenderer().render(application)["service"]["targetPort"],
                        "http" if selected == "worker" else "metrics",
                    )

    def test_service_without_declared_ports_values_and_immutability(self):
        for selection in (None, "catalog", "worker"):
            for target in (None, 9091):
                with self.subTest(selection=selection, target=target):
                    containers = [{"name": "catalog", "image": "catalog:1"}]
                    if selection == "worker":
                        containers[0]["ports"] = [{"name": "other", "port": 7070}]
                        containers += [{"name": "worker", "image": "worker:1"},
                                       {"name": "idle", "image": "idle:1"}]
                    application = Application.model_validate({
                        "name": "catalog", "containers": containers,
                        "service": {"port": 8080, "container": selection, "targetPort": target},
                    })
                    before = application.model_dump()
                    values = HelmRenderer().render(application)
                    rendered = values.get("containers", [values])
                    selected = rendered[1] if selection == "worker" else rendered[0]
                    self.assertEqual(selected["ports"], [{
                        "name": "http", "containerPort": target or 8080, "protocol": "TCP",
                    }])
                    self.assertEqual(values["service"]["targetPort"], target or "http")
                    if selection == "worker":
                        self.assertEqual(rendered[0]["ports"][0]["containerPort"], 7070)
                        self.assertEqual(rendered[2]["ports"], [])
                    self.assertEqual(application.model_dump(), before)
                    selected["ports"][0]["containerPort"] = 1234
                    self.assertEqual(application.model_dump(), before)

    def test_actual_medium_values_include_environment_and_service(self):
        application = load_application(ROOT / "examples/medium/app.yaml")
        values = HelmRenderer().render(application)
        self.assertEqual(values["env"], [
            {"name": "APP_ENV", "value": "production"},
            {"name": "LOG_LEVEL", "value": "info"},
        ])
        self.assertEqual(values["service"], {
            "enabled": True, "type": "LoadBalancer", "port": 8080, "targetPort": "http",
        })

    def test_explicit_numeric_target_port_is_preserved(self):
        application = Application.model_validate({
            "name": "catalog",
            "containers": [{"name": "catalog", "image": "catalog:1",
                            "ports": [{"name": "web", "port": 8080}]}],
            "service": {"port": 80, "targetPort": 8080},
        })
        self.assertEqual(HelmRenderer().render(application)["service"]["targetPort"], 8080)

    def test_individual_health_probes_preserve_ports_and_model_defaults(self):
        for alias, field in (("ready", "readinessProbe"), ("live", "livenessProbe"), ("startup", "startupProbe")):
            for port in (8080, "http"):
                with self.subTest(probe=alias, port=port):
                    application = health_application({alias: {"path": f"/{alias}", "port": port}})
                    before = application.model_dump()
                    values = HelmRenderer().render(application)
                    probes = {key: value for key, value in values.items() if key.endswith("Probe")}
                    self.assertEqual(probes, {field: {
                        "httpGet": {"path": f"/{alias}", "port": port},
                        "initialDelaySeconds": 0, "periodSeconds": 10,
                        "timeoutSeconds": 1, "failureThreshold": 3, "successThreshold": 1,
                    }})
                    self.assertEqual(application.model_dump(), before)

    def test_all_health_probes_preserve_explicit_timing(self):
        timing = {
            "initialDelaySeconds": 5, "timeoutSeconds": 2,
            "failureThreshold": 4, "successThreshold": 1,
        }
        application = health_application({
            "ready": {"path": "/ready", "port": "http", "frequencySeconds": 7, **timing, "successThreshold": 2},
            "live": {"path": "/live", "port": 8080, "periodSeconds": 8, **timing},
            "startup": {"path": "/startup", "port": "http", "periodSeconds": 9, **timing},
        })
        values = HelmRenderer().render(application)
        for field, path, port, period, success in (
            ("readinessProbe", "/ready", "http", 7, 2),
            ("livenessProbe", "/live", 8080, 8, 1),
            ("startupProbe", "/startup", "http", 9, 1),
        ):
            with self.subTest(probe=field):
                self.assertEqual(values[field], {
                    "httpGet": {"path": path, "port": port},
                    **timing, "periodSeconds": period, "successThreshold": success,
                })

    def test_storage_values_preserve_intent_and_defaults(self):
        for options in ({}, {"storageClass": "fast", "accessModes": ["ReadWriteMany", "ReadOnlyMany"]}):
            with self.subTest(options=options):
                application = Application.model_validate({
                    "name": "catalog",
                    "storage": {"name": "data", "size": "10Gi", **options},
                    "containers": [{"name": "catalog", "image": "catalog:1"}],
                })
                before = application.model_dump()
                self.assertEqual(HelmRenderer().render(application)["storage"], {
                    "name": "data", "size": "10Gi",
                    "accessModes": ["ReadWriteOnce"], **options,
                })
                self.assertEqual(application.model_dump(), before)
        basic = load_application(ROOT / "examples/basic/app.yaml")
        self.assertNotIn("storage", HelmRenderer().render(basic))

    def test_mount_values_preserve_sources_order_paths_and_read_only(self):
        application = mounted_application()
        before = application.model_dump()
        values = HelmRenderer().render(application)
        self.assertEqual(values["volumes"], [
            {"name": "volume-0", "secret": {"secretName": "data"}},
            {"name": "volume-1", "persistentVolumeClaim": {"claimName": "catalog-data"}},
            {"name": "volume-2", "configMap": {"name": "data"}},
        ])
        self.assertEqual(values["volumeMounts"], [
            {"name": "volume-0", "mountPath": "/etc/secrets", "readOnly": True},
            {"name": "volume-1", "mountPath": "/data"},
            {"name": "volume-2", "mountPath": "/etc/config", "readOnly": True},
            {"name": "volume-2", "mountPath": "/etc/config-copy", "readOnly": True},
            {"name": "volume-0", "mountPath": "/etc/secrets-copy", "readOnly": True},
            {"name": "volume-1", "mountPath": "/data-copy"},
        ])
        self.assertEqual(HelmRenderer().render(application), values)
        self.assertEqual(application.model_dump(), before)

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

    def test_missing_resource_files_fail_intentionally(self):
        base = {
            "name": "catalog",
            "configuration": [{"name": "config", "data": {}}],
            "containers": [{"name": "catalog", "image": "catalog:1"}],
        }
        for capability in ("file", "secrets"):
            with self.subTest(capability=capability):
                application = Application.model_validate(base)
                data = application.model_dump(by_alias=True, exclude_none=True)
                if capability == "file":
                    data["configuration"] = [{"name": "config", "file": "missing.env"}]
                else:
                    data["secrets"] = [{"name": "private", "file": "missing-secret.env"}]
                with self.assertRaisesRegex(ValueError, "Cannot read resource file"):
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

    def test_advanced_values_render_without_mutating_application(self):
        base_dir = ROOT / "examples/advanced"
        application = load_application(base_dir / "app.yaml")
        before = application.model_dump()
        with patch.dict(os.environ, {"CATALOG_API_KEY": "example-api-key"}):
            values = HelmRenderer().render(application, base_dir)
        self.assertEqual(values["service"]["targetPort"], "http")
        self.assertEqual(values["containers"][0]["ports"], [{
            "name": "http", "containerPort": 8080, "protocol": "TCP",
        }])
        self.assertEqual(values["containers"][1]["ports"], [])
        self.assertEqual(application.model_dump(), before)

    def test_unsupported_capabilities_are_not_silently_dropped(self):
        for field, value in (
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
