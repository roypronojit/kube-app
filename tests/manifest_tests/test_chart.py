"""Chart consumption of Basic values; requires Helm on PATH."""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

from kubeapp.parser import load_application
from kubeapp.renderers import HelmRenderer


ROOT = Path(__file__).resolve().parents[2]
HELM = shutil.which("helm")


@unittest.skipUnless(HELM, "Helm is required for chart template tests")
class BasicChartTests(unittest.TestCase):
    def setUp(self):
        self.values = HelmRenderer().render(
            load_application(ROOT / "examples/basic/app.yaml")
        )

    def render_chart(self):
        with tempfile.TemporaryDirectory() as directory:
            values_file = Path(directory) / "values.yaml"
            values_file.write_text(yaml.safe_dump(self.values), encoding="utf-8")
            result = subprocess.run(
                [HELM, "template", "basic-test", str(ROOT / "charts/kube-app"),
                 "-f", str(values_file)],
                capture_output=True, text=True, timeout=30,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        return {doc["kind"]: doc for doc in yaml.safe_load_all(result.stdout) if doc}

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
