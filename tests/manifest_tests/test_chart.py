"""Chart consumption of Basic values; requires Helm on PATH."""

from copy import deepcopy
import base64
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from kubeapp.parser import load_application
from kubeapp.models import Application
from kubeapp.renderers import HelmRenderer, KubernetesRenderer

from .helpers import health_application, inline_secret_application, mounted_application, multiple_container_application
from .helpers import init_container_application
from .helpers import process_application
from .test_helm_files import file_application


ROOT = Path(__file__).resolve().parents[2]
HELM = shutil.which("helm")


@unittest.skipUnless(HELM, "Helm is required for chart template tests")
class BasicChartTests(unittest.TestCase):
    def setUp(self):
        self.application = load_application(ROOT / "examples/basic/app.yaml")
        self.values = HelmRenderer().render(self.application)

    def render_documents(self):
        with tempfile.TemporaryDirectory() as directory:
            values_file = Path(directory) / "values.yaml"
            values_file.write_text(yaml.safe_dump(self.values), encoding="utf-8")
            result = subprocess.run(
                [HELM, "template", "basic-test", str(ROOT / "charts/kube-app"),
                 "-f", str(values_file)],
                capture_output=True, text=True, timeout=30,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        return [doc for doc in yaml.safe_load_all(result.stdout) if doc is not None]

    def render_chart(self):
        return {doc["kind"]: doc for doc in self.render_documents()}

    def test_service_targets_explicit_application_container(self):
        for target in (None, "metrics", 9090):
            with self.subTest(target=target):
                data = multiple_container_application().model_dump(by_alias=True)
                data["service"] = {"port": 80, "container": "metrics", "targetPort": target}
                application = Application.model_validate(data)
                before = application.model_dump()
                self.values = HelmRenderer().render(application)
                documents = self.render_documents()
                service = next(doc for doc in documents if doc["kind"] == "Service")
                expected = next(doc for doc in KubernetesRenderer().render(application) if doc["kind"] == "Service")
                self.assertEqual(service["spec"], expected["spec"])
                self.assertEqual(service["spec"]["ports"][0]["targetPort"], target or "metrics")
                pod = next(doc for doc in documents if doc["kind"] == "Deployment")["spec"]["template"]["spec"]
                self.assertEqual(pod["containers"][0]["ports"][0]["containerPort"], 8080)
                self.assertEqual(pod["containers"][1]["ports"][0]["containerPort"], 9090)
                self.assertNotIn("ports", pod["containers"][2])
                self.assertEqual(application.model_dump(), before)

    def test_application_service_account_is_referenced_not_created(self):
        for name in (None, "catalog.identity", "true"):
            with self.subTest(name=name):
                data = init_container_application().model_dump(by_alias=True)
                data["serviceAccount"] = name
                application = Application.model_validate(data)
                before = application.model_dump()
                self.values = HelmRenderer().render(application)
                documents = self.render_documents()
                self.assertCountEqual([doc["kind"] for doc in documents], ["Deployment", "ConfigMap", "Secret", "PersistentVolumeClaim"])
                pod = next(doc for doc in documents if doc["kind"] == "Deployment")["spec"]["template"]["spec"]
                reference = next(doc for doc in KubernetesRenderer().render(application) if doc["kind"] == "Deployment")["spec"]["template"]["spec"]
                self.assertEqual(pod["serviceAccountName"], name if name is not None else "default")
                self.assertEqual(pod["serviceAccountName"], reference.get("serviceAccountName", "default"))
                self.assertEqual(len(pod["initContainers"]), 2)
                self.assertEqual(len(pod["containers"]), 3)
                for container in [*pod["initContainers"], *pod["containers"]]:
                    self.assertNotIn("serviceAccountName", container)
                self.assertEqual(application.model_dump(), before)

    def test_command_args_for_application_and_init_containers(self):
        application = process_application()
        self.values = HelmRenderer().render(application)
        pod = self.render_chart()["Deployment"]["spec"]["template"]["spec"]
        for field, models in (("containers", application.containers), ("initContainers", application.init)):
            self.assertEqual([c["name"] for c in pod[field]], [c.name for c in models])
            for rendered, model in zip(pod[field], models):
                with self.subTest(container=model.name):
                    for key in ("command", "args"):
                        expected = getattr(model, key)
                        if expected is None:
                            self.assertNotIn(key, rendered)
                        else:
                            self.assertEqual(rendered[key], expected)

    def test_init_containers_share_resources_and_preserve_order(self):
        for count in (1, 2):
            with self.subTest(count=count):
                application = init_container_application(count)
                self.values = HelmRenderer().render(application)
                documents = self.render_documents()
                self.assertCountEqual([doc["kind"] for doc in documents], ["Deployment", "ConfigMap", "Secret", "PersistentVolumeClaim"])
                pod = next(doc for doc in documents if doc["kind"] == "Deployment")["spec"]["template"]["spec"]
                expected = next(doc for doc in KubernetesRenderer().render(application) if doc["kind"] == "Deployment")["spec"]["template"]["spec"]
                self.assertEqual([c["name"] for c in pod["initContainers"]], ["prepare", "verify"][:count])
                self.assertEqual(pod["initContainers"], expected["initContainers"])
                self.assertEqual(pod["volumes"], expected["volumes"])
                self.assertEqual(len(pod["volumes"]), 3)
                for actual, reference in zip(pod["containers"], expected["containers"]):
                    self.assertEqual(actual.get("volumeMounts"), reference.get("volumeMounts"))
        self.values = HelmRenderer().render(self.application)
        self.assertNotIn("initContainers", self.values)
        pod = self.render_chart()["Deployment"]["spec"]["template"]["spec"]
        self.assertNotIn("initContainers", pod)

    def test_multiple_containers_and_shared_resources(self):
        application = multiple_container_application()
        self.values = HelmRenderer().render(application)
        documents = self.render_documents()
        self.assertCountEqual([doc["kind"] for doc in documents], ["Deployment", "ConfigMap", "Secret", "PersistentVolumeClaim"])
        pod = next(doc for doc in documents if doc["kind"] == "Deployment")["spec"]["template"]["spec"]
        expected = next(doc for doc in KubernetesRenderer().render(application) if doc["kind"] == "Deployment")["spec"]["template"]["spec"]
        self.assertEqual([c["name"] for c in pod["containers"]], ["catalog", "metrics", "worker"])
        for container in expected["containers"]:
            container.setdefault("resources", {})  # Empty and omitted requests/limits are equivalent.
        self.assertEqual(pod["containers"], expected["containers"])
        self.assertEqual(pod["volumes"], expected["volumes"])
        self.assertEqual(len(pod["volumes"]), 3)

    def test_file_resources_render_to_configmap_and_secret(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "inputs").mkdir()
            (base / "inputs/config.properties").write_text("MODE=${HELM_FILE_VALUE}\n", encoding="utf-8")
            (base / "inputs/secret.env").write_text("TOKEN=${HELM_FILE_VALUE}\n", encoding="utf-8")
            application = file_application(base)
            with patch.dict(os.environ, {"HELM_FILE_VALUE": "demonstration"}):
                self.values = HelmRenderer().render(application, base)
        # Helm receives resolved data and does not need access to the source files.
        documents = self.render_chart()
        self.assertEqual(set(documents), {"Deployment", "ConfigMap", "Secret"})
        self.assertEqual(documents["ConfigMap"]["metadata"]["name"], "settings")
        self.assertEqual(documents["ConfigMap"]["data"], {"MODE": "demonstration"})
        self.assertEqual(documents["Secret"]["metadata"]["name"], "credentials")
        self.assertEqual(documents["Secret"]["type"], "Opaque")
        self.assertEqual(documents["Secret"]["stringData"], {"TOKEN": "demonstration"})

    def test_actual_medium_end_to_end_and_semantic_equivalence(self):
        source = ROOT / "examples/medium/app.yaml"
        application = load_application(source)
        before = application.model_dump()
        self.values = HelmRenderer().render(application, source.parent)
        helm = self.render_documents()  # Checks exit status and parses all YAML.
        self.assertCountEqual(
            [doc["kind"] for doc in helm],
            ["Deployment", "Service", "ConfigMap", "Secret", "PersistentVolumeClaim"],
        )
        kubernetes = KubernetesRenderer().render(application, source.parent)

        def semantic_resource(document):
            result = deepcopy(document)
            # Ignore only descriptive resource labels, never selectors/pod labels.
            for key in ("helm.sh/chart", "app.kubernetes.io/managed-by", "app.kubernetes.io/version"):
                result["metadata"]["labels"].pop(key, None)
            if result["kind"] == "Deployment":
                result["spec"]["template"]["spec"].setdefault("serviceAccountName", "default")
            if result["kind"] == "Secret":
                data = {key: base64.b64decode(value, validate=True) for key, value in result.pop("data", {}).items()}
                data.update({key: value.encode("utf-8") for key, value in result.pop("stringData", {}).items()})
                result["data"] = data
            return result

        expected = {(doc["kind"], doc["metadata"]["name"]): semantic_resource(doc) for doc in kubernetes}
        actual = {(doc["kind"], doc["metadata"]["name"]): semantic_resource(doc) for doc in helm}
        self.assertEqual(set(actual), set(expected))
        for identity in expected:
            with self.subTest(resource=identity):
                self.assertEqual(actual[identity], expected[identity])
        self.assertEqual(application.model_dump(), before)

    def test_http_probes_match_kubernetes_probe_semantics(self):
        probes = {
            "ready": {"path": "/ready", "port": "http", "successThreshold": 2},
            "live": {"path": "/live", "port": 8080},
            "startup": {
                "path": "/startup", "port": "http", "initialDelaySeconds": 5,
                "frequencySeconds": 7, "timeoutSeconds": 2,
                "failureThreshold": 8, "successThreshold": 1,
            },
        }
        for declared in (("ready",), ("live",), ("startup",), tuple(probes)):
            with self.subTest(declared=declared):
                application = health_application({name: probes[name] for name in declared})
                self.values = HelmRenderer().render(application)
                documents = self.render_documents()
                self.assertEqual([doc["kind"] for doc in documents], ["Deployment"])
                container = documents[0]["spec"]["template"]["spec"]["containers"][0]
                reference = KubernetesRenderer().render(application)[0]["spec"]["template"]["spec"]["containers"][0]
                self.assertEqual(
                    {key: value for key, value in container.items() if key.endswith("Probe")},
                    {key: value for key, value in reference.items() if key.endswith("Probe")},
                )
        self.values = HelmRenderer().render(self.application)
        container = self.render_chart()["Deployment"]["spec"]["template"]["spec"]["containers"][0]
        self.assertFalse(any(key.endswith("Probe") for key in container))

    def test_resource_mounts_match_kubernetes_mount_semantics(self):
        application = mounted_application()
        self.values = HelmRenderer().render(application)
        documents = self.render_documents()
        self.assertCountEqual(
            [doc["kind"] for doc in documents],
            ["Deployment", "ConfigMap", "Secret", "PersistentVolumeClaim"],
        )
        resources = {doc["kind"]: doc for doc in documents}
        pod = resources["Deployment"]["spec"]["template"]["spec"]
        reference = next(
            doc for doc in KubernetesRenderer().render(application)
            if doc["kind"] == "Deployment"
        )["spec"]["template"]["spec"]
        self.assertEqual(pod["volumes"], reference["volumes"])
        mounts = pod["containers"][0]["volumeMounts"]
        self.assertEqual(mounts, reference["containers"][0]["volumeMounts"])
        self.assertEqual(pod["volumes"][0]["secret"]["secretName"], resources["Secret"]["metadata"]["name"])
        self.assertEqual(pod["volumes"][1]["persistentVolumeClaim"]["claimName"], resources["PersistentVolumeClaim"]["metadata"]["name"])
        self.assertEqual(pod["volumes"][2]["configMap"]["name"], resources["ConfigMap"]["metadata"]["name"])
        self.assertEqual([mount.get("readOnly", False) for mount in mounts], [True, False, True, True, True, False])

    def test_storage_pvc_matches_kubernetes_semantics(self):
        for options in ({}, {"storageClass": "fast", "accessModes": ["ReadWriteMany", "ReadOnlyMany"]}):
            with self.subTest(options=options):
                application = Application.model_validate({
                    "name": "catalog",
                    "storage": {"name": "data", "size": "10Gi", **options},
                    "containers": [{"name": "catalog", "image": "catalog:1"}],
                })
                self.values = HelmRenderer().render(application)
                documents = self.render_documents()
                self.assertCountEqual(
                    [doc["kind"] for doc in documents],
                    ["Deployment", "PersistentVolumeClaim"],
                )
                pvc = next(doc for doc in documents if doc["kind"] == "PersistentVolumeClaim")
                expected = next(
                    doc for doc in KubernetesRenderer().render(application)
                    if doc["kind"] == "PersistentVolumeClaim"
                )
                self.assertEqual(pvc["apiVersion"], "v1")
                self.assertEqual(pvc["metadata"]["name"], "catalog-data")
                self.assertEqual(pvc["metadata"]["name"], expected["metadata"]["name"])
                self.assertEqual(pvc["spec"], expected["spec"])
                self.assertEqual(pvc["spec"]["resources"], {"requests": {"storage": "10Gi"}})
                self.assertEqual(pvc["spec"]["accessModes"], options.get("accessModes", ["ReadWriteOnce"]))
                if "storageClass" in options:
                    self.assertEqual(pvc["spec"]["storageClassName"], "fast")
                else:
                    self.assertNotIn("storageClassName", pvc["spec"])
                pod = next(doc for doc in documents if doc["kind"] == "Deployment")["spec"]["template"]["spec"]
                self.assertNotIn("volumes", pod)
                self.assertNotIn("volumeMounts", pod["containers"][0])
        self.values = HelmRenderer().render(self.application)
        self.assertNotIn("PersistentVolumeClaim", self.render_chart())

    def test_inline_secrets_and_environment_consumption(self):
        application = inline_secret_application()
        with patch.dict(os.environ, {"HELM_TEST_PASSWORD": "example"}):
            self.values = HelmRenderer().render(application)
            expected = [
                doc for doc in KubernetesRenderer().render(application)
                if doc["kind"] == "Secret"
            ]
        documents = self.render_documents()
        self.assertCountEqual(
            [doc["kind"] for doc in documents],
            ["Deployment", "ConfigMap", "Secret", "Secret", "Secret"],
        )
        secrets = [doc for doc in documents if doc["kind"] == "Secret"]
        self.assertEqual(
            [doc["metadata"]["name"] for doc in secrets],
            ["z-db", "a-api", "unused-secret"],
        )
        for secret, reference in zip(secrets, expected):
            with self.subTest(name=secret["metadata"]["name"]):
                self.assertEqual(secret["apiVersion"], "v1")
                self.assertEqual(secret["type"], "Opaque")
                self.assertEqual(secret["stringData"], reference["stringData"])
                self.assertNotIn("data", secret)
                self.assertEqual(secret["metadata"]["labels"]["app.kubernetes.io/name"], "catalog")
        configmap = next(doc for doc in documents if doc["kind"] == "ConfigMap")
        self.assertEqual(configmap["data"], {"APP_ENV": "test"})
        deployment = next(doc for doc in documents if doc["kind"] == "Deployment")
        container = deployment["spec"]["template"]["spec"]["containers"][0]
        self.assertEqual(container["envFrom"], [
            {"configMapRef": {"name": "catalog-config"}},
            {"secretRef": {"name": "a-api"}},
            {"secretRef": {"name": "z-db"}},
        ])

    def test_configuration_maps_and_environment_consumption(self):
        application = Application.model_validate({
            "name": "catalog",
            "configuration": [
                {"name": "catalog-config", "data": {
                    "APP_ENV": "production", "COUNT": 3, "ENABLED": False,
                    "MULTILINE": "first\nsecond\n", "LITERAL": "{{ .Release.Name }}",
                }},
                {"name": "logging-config", "data": {"LOG_LEVEL": "info"}},
                {"name": "unused-config", "data": {}},
            ],
            "containers": [{
                "name": "catalog", "image": "catalog:1.4.2",
                "configuration": [
                    {"name": "logging-config", "as": "environment"},
                    {"name": "catalog-config", "as": "environment"},
                ],
            }],
        })
        self.values = HelmRenderer().render(application)
        documents = self.render_documents()
        self.assertCountEqual(
            [doc["kind"] for doc in documents],
            ["Deployment", "ConfigMap", "ConfigMap", "ConfigMap"],
        )
        configmaps = {doc["metadata"]["name"]: doc for doc in documents if doc["kind"] == "ConfigMap"}
        self.assertEqual(set(configmaps), {"catalog-config", "logging-config", "unused-config"})
        self.assertEqual(configmaps["catalog-config"]["data"], {
            "APP_ENV": "production", "COUNT": "3", "ENABLED": "false",
            "MULTILINE": "first\nsecond\n", "LITERAL": "{{ .Release.Name }}",
        })
        self.assertEqual(configmaps["logging-config"]["data"], {"LOG_LEVEL": "info"})
        self.assertEqual(configmaps["unused-config"]["data"], {})
        for configmap in configmaps.values():
            self.assertEqual(configmap["apiVersion"], "v1")
            self.assertEqual(configmap["metadata"]["labels"]["app.kubernetes.io/name"], "catalog")
        deployment = next(doc for doc in documents if doc["kind"] == "Deployment")
        container = deployment["spec"]["template"]["spec"]["containers"][0]
        self.assertEqual(container["envFrom"], [
            {"configMapRef": {"name": "logging-config"}},
            {"configMapRef": {"name": "catalog-config"}},
        ])

    def test_basic_end_to_end_produces_only_deployment_and_service(self):
        documents = self.render_documents()
        self.assertCountEqual(
            [doc["kind"] for doc in documents], ["Deployment", "Service"]
        )
        for document in documents:
            with self.subTest(kind=document["kind"]):
                self.assertEqual(
                    document["apiVersion"],
                    "apps/v1" if document["kind"] == "Deployment" else "v1",
                )
                self.assertTrue(document["metadata"]["name"])
                self.assertIsInstance(document["spec"], dict)

    def test_basic_renderers_are_semantically_equivalent(self):
        kubernetes = KubernetesRenderer().render(self.application)
        helm = self.render_documents()
        self.assertCountEqual(
            [doc["kind"] for doc in helm], [doc["kind"] for doc in kubernetes]
        )
        expected = {doc["kind"]: doc for doc in kubernetes}
        for document in helm:
            actual = deepcopy(document)
            reference = deepcopy(expected[actual["kind"]])
            # Only descriptive labels on resource metadata are ignored. Pod
            # labels and every selector remain intact and must match exactly.
            for key in (
                "helm.sh/chart", "app.kubernetes.io/managed-by",
                "app.kubernetes.io/version",
            ):
                actual["metadata"]["labels"].pop(key, None)
            if actual["kind"] == "Deployment":
                # Kubernetes uses the namespace's default service account
                # when serviceAccountName is omitted.
                for resource in (actual, reference):
                    resource["spec"]["template"]["spec"].setdefault(
                        "serviceAccountName", "default"
                    )
            for field in ("apiVersion", "metadata", "spec"):
                with self.subTest(kind=actual["kind"], field=field):
                    self.assertEqual(actual[field], reference[field])
            with self.subTest(kind=actual["kind"], field="resource fields"):
                self.assertEqual(set(actual), set(reference))

    def test_basic_values_are_consumed(self):
        for port_name in ("http", "web"):
            with self.subTest(port_name=port_name):
                self.values["ports"][0]["name"] = port_name
                self.values["service"]["targetPort"] = port_name
                documents = self.render_chart()
                deployment = documents["Deployment"]
                self.assertEqual(deployment["metadata"]["name"], "hello-world")
                self.assertEqual(deployment["spec"]["replicas"], 2)
                pod = deployment["spec"]["template"]["spec"]
                self.assertEqual(pod["serviceAccountName"], "default")
                self.assertEqual(pod["containers"], [{
                    "name": "hello-world",
                    "image": "nginxinc/nginx-unprivileged:1.27",
                    "imagePullPolicy": "IfNotPresent",
                    "ports": self.values["ports"],
                    "resources": self.values["resources"],
                }])
                service = documents["Service"]["spec"]
                self.assertEqual(service["type"], "ClusterIP")
                self.assertEqual(service["ports"], [{
                    "port": 80, "targetPort": port_name,
                    "protocol": "TCP", "name": "http",
                }])
                self.assertNotIn("ServiceAccount", documents)

    def test_disabled_service_empty_ports_and_service_account_creation(self):
        self.values.update(replicaCount=0, ports=[], resources={})
        self.values["service"] = {"enabled": False}
        self.values["serviceAccount"] = {"create": True}
        documents = self.render_chart()
        self.assertEqual(set(documents), {"Deployment", "ServiceAccount"})
        deployment = documents["Deployment"]["spec"]
        self.assertEqual(deployment["replicas"], 0)
        pod = deployment["template"]["spec"]
        self.assertNotIn("ports", pod["containers"][0])
        self.assertEqual(pod["containers"][0]["resources"], {})
        self.assertEqual(
            pod["serviceAccountName"], documents["ServiceAccount"]["metadata"]["name"]
        )
