"""Chart consumption of Basic values; requires Helm on PATH."""

from copy import deepcopy
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

from kubeapp.parser import load_application
from kubeapp.renderers import HelmRenderer, KubernetesRenderer


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
