import copy
import unittest

from pydantic import ValidationError

from kubeapp.manifests import application_to_kubernetes_manifests
from kubeapp.models import Application


class RuntimeTests(unittest.TestCase):
    def test_sctp_ports_render_but_cannot_receive_service_traffic(self):
        app = self.application(ports=[{"name": "signals", "port": 9000, "protocol": "SCTP"}])
        self.assertEqual(self.pod(app)["containers"][0]["ports"], [
            {"name": "signals", "containerPort": 9000, "protocol": "SCTP"},
        ])
        for target in (None, "signals", 9000):
            data = app.model_dump(by_alias=True, exclude_none=True)
            data["service"] = {"port": 80}
            if target is not None:
                data["service"]["targetPort"] = target
            with self.subTest(target=target), self.assertRaises(ValidationError):
                Application.model_validate(data)

    def application(self, **fields):
        return Application.model_validate(
            {
                "name": "app",
                "containers": [{"name": "app", "image": "app:1", **fields}],
            }
        )

    def render(self, application):
        return application_to_kubernetes_manifests(application)

    def pod(self, application):
        return self.render(application)[0]["spec"]["template"]["spec"]

    def test_security_context_is_not_injected_into_pod_or_containers(self):
        data = self.application().model_dump(by_alias=True, exclude_none=True)
        data["init"] = [{"name": "init", "image": "init:1"}]
        pod = self.pod(Application.model_validate(data))
        self.assertNotIn("securityContext", pod)
        for c in pod["containers"] + pod["initContainers"]:
            self.assertNotIn("securityContext", c)
            self.assertEqual(c["imagePullPolicy"], "IfNotPresent")
            for key in (
                "command",
                "args",
                "ports",
                "livenessProbe",
                "readinessProbe",
                "startupProbe",
            ):
                self.assertNotIn(key, c)

    def test_security_fields_are_not_public(self):
        for field in (
            "securityContext",
            "runAsUser",
            "privileged",
            "allowPrivilegeEscalation",
        ):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                self.application(**{field: {}})
        data = {
            "name": "app",
            "containers": [{"name": "app", "image": "app:1"}],
            "securityContext": {},
        }
        with self.assertRaises(ValidationError):
            Application.model_validate(data)

    def test_commands_are_preserved_on_containers_and_init(self):
        fields = {
            "command": ["/bin/sh", "-c"],
            "args": ["echo $VALUE", "", "--flag=value"],
        }
        data = self.application(**fields).model_dump(by_alias=True, exclude_none=True)
        data["init"] = [{"name": "init", "image": "init:1", **fields}]
        pod = self.pod(Application.model_validate(data))
        for c in pod["containers"] + pod["initContainers"]:
            for key, value in fields.items():
                self.assertEqual(c[key], value)

    def test_args_can_override_image_defaults_without_command(self):
        c = self.pod(self.application(args=["--serve"]))["containers"][0]
        self.assertEqual(c["args"], ["--serve"])
        self.assertNotIn("command", c)

    def test_pull_policy_values(self):
        for policy in ("Always", "Never", "IfNotPresent"):
            with self.subTest(policy=policy):
                self.assertEqual(
                    self.pod(self.application(imagePullPolicy=policy))["containers"][0][
                        "imagePullPolicy"
                    ],
                    policy,
                )

    def test_ports_without_service_and_protocols(self):
        ports = [
            {"name": "web", "port": 8080},
            {"name": "dns", "port": 53, "protocol": "UDP"},
        ]
        app = self.application(ports=ports)
        self.assertEqual(len(self.render(app)), 1)
        self.assertEqual(
            self.pod(app)["containers"][0]["ports"],
            [
                {"name": "web", "containerPort": 8080, "protocol": "TCP"},
                {"name": "dns", "containerPort": 53, "protocol": "UDP"},
            ],
        )

    def test_service_targets_declared_port_by_name_or_number(self):
        for target in ("web", 8080):
            data = self.application(ports=[{"name": "web", "port": 8080}]).model_dump(
                by_alias=True, exclude_none=True
            )
            data["service"] = {"port": 80, "targetPort": target}
            manifests = self.render(Application.model_validate(data))
            self.assertEqual(manifests[-1]["spec"]["ports"][0]["targetPort"], target)
            self.assertEqual(manifests[-1]["spec"]["ports"][0]["port"], 80)

    def test_service_without_explicit_ports_keeps_inferred_port(self):
        data = self.application().model_dump(by_alias=True, exclude_none=True)
        data["service"] = {"port": 80}
        manifests = self.render(Application.model_validate(data))
        self.assertEqual(
            manifests[0]["spec"]["template"]["spec"]["containers"][0]["ports"][0][
                "containerPort"
            ],
            80,
        )
        self.assertEqual(manifests[-1]["spec"]["ports"][0]["targetPort"], "http")

    def test_probes_render_independently_with_timing(self):
        for kind in ("readiness", "liveness", "startup"):
            with self.subTest(kind=kind):
                app = self.application(
                    ports=[{"name": "web", "port": 8080}],
                    health={
                        kind: {
                            "path": "/health",
                            "port": "web",
                            "initialDelaySeconds": 4,
                            "periodSeconds": 5,
                            "timeoutSeconds": 2,
                            "failureThreshold": 120 if kind == "startup" else 6,
                        }
                    },
                )
                c = self.pod(app)["containers"][0]
                self.assertEqual(
                    c[kind + "Probe"],
                    {
                        "httpGet": {"path": "/health", "port": "web"},
                        "initialDelaySeconds": 4,
                        "periodSeconds": 5,
                        "timeoutSeconds": 2,
                        "failureThreshold": 120 if kind == "startup" else 6,
                        "successThreshold": 1,
                    },
                )
                self.assertEqual(sum(key.endswith("Probe") for key in c), 1)

    def test_readiness_success_threshold_and_numeric_probe_port(self):
        app = self.application(
            health={"readiness": {"path": "/", "port": 8080, "successThreshold": 2}}
        )
        probe = self.pod(app)["containers"][0]["readinessProbe"]
        self.assertEqual(probe["successThreshold"], 2)
        self.assertEqual(probe["httpGet"]["port"], 8080)

    def test_example_health_aliases(self):
        for field in ("healthCheck", "healthChecks"):
            with self.subTest(field=field):
                c = self.pod(self.application(**{field: {
                    "ready": {"path": "/ready", "port": 8080, "frequencySeconds": 7},
                    "live": {"path": "/live", "port": 8080},
                    "startup": {"path": "/start", "port": 8080},
                }}))["containers"][0]
                self.assertEqual(c["readinessProbe"]["periodSeconds"], 7)
                self.assertEqual(c["livenessProbe"]["httpGet"]["path"], "/live")
                self.assertEqual(c["startupProbe"]["httpGet"]["path"], "/start")
                self.assertNotIn("frequencySeconds", c["readinessProbe"])
        for value in (0, -1, True, "5"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                self.application(healthChecks={"ready": {
                    "path": "/", "port": 80, "frequencySeconds": value,
                }})

    def test_service_infers_sole_tcp_port(self):
        data = {
            "name": "app",
            "containers": [{"name": "app", "image": "app:1", "ports": [
                {"name": "web", "port": 8080},
            ]}],
            "service": {"port": 80},
        }
        manifests = self.render(Application.model_validate(data))
        self.assertEqual(manifests[-1]["spec"]["ports"][0]["targetPort"], "web")
        data["containers"][0]["ports"].append({"name": "metrics", "port": 9090})
        with self.assertRaisesRegex(ValidationError, "targetPort is required"):
            Application.model_validate(data)

    def test_invalid_runtime_fields(self):
        cases = [
            {"command": "echo hello"},
            {"command": []},
            {"command": [""]},
            {"args": "--serve"},
            {"args": []},
            {"args": [1]},
            {"imagePullPolicy": "always"},
        ]
        for fields in cases:
            with self.subTest(fields=fields), self.assertRaises(ValidationError):
                self.application(**fields)

    def test_invalid_ports(self):
        cases = [{"name": "web", "port": n} for n in (0, 65536, True, "8080", 1.5)]
        cases += [
            {"name": n, "port": 8080} for n in ("", "UPPER", "a" * 16, "bad_name", "1")
        ]
        cases += [{"name": "web", "port": 8080, "protocol": "HTTP"}]
        for port in cases:
            with self.subTest(port=port), self.assertRaises(ValidationError):
                self.application(ports=[port])
        for ports in (
            [{"name": "web", "port": 80}, {"name": "web", "port": 81}],
            [{"name": "web", "port": 80}, {"name": "other", "port": 80}],
        ):
            with self.assertRaises(ValidationError):
                self.application(ports=ports)

    def test_invalid_probes(self):
        probes = [
            {"path": "/", "port": 8080, key: value}
            for key, value in (
                ("initialDelaySeconds", -1),
                ("periodSeconds", 0),
                ("timeoutSeconds", 0),
                ("failureThreshold", 0),
                ("successThreshold", 0),
                ("periodSeconds", True),
                ("path", "relative"),
                ("port", 0),
                ("port", "missing"),
                ("unknown", 1),
            )
        ]
        for probe in probes:
            with self.subTest(probe=probe), self.assertRaises(ValidationError):
                self.application(health={"readiness": probe})
        for kind in ("liveness", "startup"):
            with self.assertRaises(ValidationError):
                self.application(
                    health={kind: {"path": "/", "port": 80, "successThreshold": 2}}
                )
        with self.assertRaises(ValidationError):
            self.application(health={})

    def test_init_probes_rejected(self):
        data = self.application().model_dump(by_alias=True, exclude_none=True)
        data["init"] = [
            {
                "name": "init",
                "image": "init:1",
                "health": {"readiness": {"path": "/", "port": 80}},
            }
        ]
        with self.assertRaises(ValidationError):
            Application.model_validate(data)

    def test_service_rejects_missing_or_non_tcp_target(self):
        for target in ("missing", 9000, "dns"):
            data = self.application(
                ports=[{"name": "dns", "port": 53, "protocol": "UDP"}]
            ).model_dump(by_alias=True, exclude_none=True)
            data["service"] = {"port": 80, "targetPort": target}
            with self.subTest(target=target), self.assertRaises(ValidationError):
                Application.model_validate(data)

    def test_render_is_deterministic_and_does_not_mutate_model(self):
        app = self.application(
            command=["serve"], health={"readiness": {"path": "/", "port": 80}}
        )
        before = copy.deepcopy(app.model_dump())
        self.assertEqual(self.render(app), self.render(app))
        self.assertEqual(app.model_dump(), before)
