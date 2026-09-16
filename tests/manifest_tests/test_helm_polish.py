"""Reference contract coverage and safe optional-resource omission."""

import os
import unittest
from unittest.mock import patch

from kubeapp.chart_inspection import inspect_chart
from kubeapp.diagnostics import helm_messages
from kubeapp.models import Application
from kubeapp.parser import load_application
from kubeapp.renderers import HelmRenderer, KubernetesRenderer
from kubeapp.value_mapping import compare_values
from .helpers import PROJECT_ROOT


class HelmPolishTests(unittest.TestCase):
    def test_service_types_pass_through_model_and_both_outputs(self):
        for service_type in ("ClusterIP", "NodePort", "LoadBalancer"):
            for target in (8080, "http"):
                with self.subTest(service_type=service_type, target=target):
                    application = Application.model_validate({
                        "name": "app", "containers": [{"name": "web", "image": "nginx:1",
                            "ports": [{"name": "http", "port": 8080}]}],
                        "service": {"type": service_type, "port": 80, "targetPort": target},
                    })
                    before = application.model_dump()
                    self.assertEqual(application.service.type, service_type)
                    service = next(doc for doc in KubernetesRenderer().render(application) if doc["kind"] == "Service")
                    self.assertEqual(service["spec"]["type"], service_type)
                    self.assertEqual(service["spec"]["ports"], [{"name": "http", "port": 80,
                                                               "targetPort": target, "protocol": "TCP"}])
                    values = HelmRenderer().render(application)
                    self.assertEqual(values["service"], {"enabled": True, "type": service_type,
                                                         "port": 80, "targetPort": target})
                    self.assertEqual(helm_messages(compare_values(values, inspect_chart(
                        PROJECT_ROOT / "charts/kube-app", application))), ())
                    self.assertEqual(application.model_dump(), before)

    def test_reference_contract_covers_examples_without_diagnostics(self):
        with patch.dict(os.environ, {"CATALOG_API_KEY": "test-api-key"}):
            for name in ("basic", "medium", "advanced"):
                with self.subTest(example=name):
                    source = PROJECT_ROOT / "examples" / name / "app.yaml"
                    application = load_application(source)
                    before = application.model_dump()
                    values = HelmRenderer().render(application, source.parent)
                    result = compare_values(values, inspect_chart(PROJECT_ROOT / "charts/kube-app", application))
                    self.assertEqual(helm_messages(result), ())
                    self.assertEqual(application.model_dump(), before)
                    if name == "advanced":
                        self.assertNotIn("resources", values["initContainers"][0])
                        manifests = KubernetesRenderer().render(application, source.parent)
                        pod = next(doc for doc in manifests if doc["kind"] == "Deployment")["spec"]["template"]["spec"]
                        for generated, expected in zip(values["containers"], pod["containers"]):
                            self.assertEqual(generated["resources"], expected["resources"])

    def test_optional_resources_omitted_for_all_container_shapes(self):
        for declared in (None, {}):
            for multiple in (False, True):
                with self.subTest(declared=declared, multiple=multiple):
                    container = {"name": "web", "image": "nginx:1"}
                    if declared is not None:
                        container["resources"] = declared
                    data = {"name": "app", "containers": [container],
                            "init": [dict(container, name="prepare")]}
                    if multiple:
                        data["containers"].append({"name": "metrics", "image": "metrics:1",
                                                   "resources": {"cpu": {"min": "50m", "max": "100m"}}})
                    application = Application.model_validate(data)
                    before = application.model_dump()
                    values = HelmRenderer().render(application)
                    first = values["containers"][0] if multiple else values
                    self.assertNotIn("resources", first)
                    self.assertNotIn("resources", values["initContainers"][0])
                    self.assertEqual(first["ports"], [])  # Overrides reference chart defaults.
                    self.assertEqual(values["service"], {"enabled": False})
                    self.assertEqual(values["serviceAccount"], {"create": False})
                    if multiple:
                        self.assertEqual(values["containers"][1]["resources"],
                                         {"requests": {"cpu": "50m"}, "limits": {"cpu": "100m"}})
                    self.assertEqual(application.model_dump(), before)
