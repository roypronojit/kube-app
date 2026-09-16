import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import yaml

from kubeapp.cli import build_parser, main
from kubeapp.parser import load_application
from kubeapp.renderers import KubernetesRenderer

from .helpers import PROJECT_ROOT, temporary_chart


class ValidateCommandTests(unittest.TestCase):
    def test_no_subcommand_exits_with_usage_error(self):
        errors = io.StringIO()
        with patch.object(sys, "argv", ["kube-app"]), redirect_stderr(errors):
            with self.assertRaises(SystemExit) as raised:
                main()
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("usage:", errors.getvalue())

    def test_module_entry_point(self):
        source = PROJECT_ROOT / "examples/basic/app.yaml"
        for command in ("render", "validate"):
            with self.subTest(command=command):
                result = subprocess.run(
                    [sys.executable, "-m", "kubeapp", command, str(source)],
                    cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=30,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stderr, "")
                if command == "validate":
                    self.assertEqual(result.stdout, "Application 'hello-world' is valid.\n")
                else:
                    self.assertEqual(
                        [m["kind"] for m in yaml.safe_load_all(result.stdout)],
                        ["Deployment", "Service"],
                    )

    def test_valid_application(self):
        source = PROJECT_ROOT / "examples/basic/app.yaml"
        output, errors = io.StringIO(), io.StringIO()
        with (
            patch.object(sys, "argv", ["kube-app", "validate", str(source)]),
            redirect_stdout(output),
            redirect_stderr(errors),
        ):
            self.assertEqual(main(), 0)
        self.assertEqual(output.getvalue(), "Application 'hello-world' is valid.\n")
        self.assertEqual(errors.getvalue(), "")

    def test_invalid_application_reports_error_and_exit_code(self):
        for content, message in (
            (None, "does not exist"),
            ("name: [\n", "Invalid YAML"),
            ("name: worker\ncontainers: []\n", "Invalid application definition"),
        ):
            with self.subTest(content=content), tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / "app.yaml"
                if content is not None:
                    source.write_text(content, encoding="utf-8")
                output, errors = io.StringIO(), io.StringIO()
                with (
                    patch.object(sys, "argv", ["kube-app", "validate", str(source)]),
                    redirect_stdout(output),
                    redirect_stderr(errors),
                ):
                    self.assertEqual(main(), 1)
                self.assertEqual(output.getvalue(), "")
                self.assertIn(message, errors.getvalue())


class RenderContractTests(unittest.TestCase):
    """CLI contract checks using isolated inputs, independent of examples."""

    def setUp(self):
        self.chart = temporary_chart(self)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.base = Path(directory.name)
        self.source = self.base / "app.yaml"
        self.source.write_text(yaml.safe_dump({
            "name": "original", "serviceAccount": "explicit-account",
            "containers": [{"name": "web", "image": "nginx:1.27",
                            "mounts": [{"storage": "data", "path": "/data"}]}],
            "init": [{"name": "prepare", "image": "busybox:1.36"}],
            "configuration": [{"name": "explicit-config", "data": {"KEY": "value"}}],
            "secrets": [{"name": "explicit-secret", "data": {"KEY": "value"}}],
            "storage": {"name": "data", "size": "1Gi"},
            "service": {"port": 80},
        }), encoding="utf-8")

    def invoke(self, *arguments):
        if any(arguments[index:index + 2] == ("-f", alias)
               or arguments[index:index + 2] == ("--format", alias)
               for index in range(len(arguments)) for alias in ("helm", "h")):
            arguments = (*arguments, "--chart", str(self.chart))
        output, errors = io.StringIO(), io.StringIO()
        with (patch.object(sys, "argv", ["kube-app", "render", str(self.source), *arguments]),
              redirect_stdout(output), redirect_stderr(errors)):
            result = main()
        return result, output.getvalue(), errors.getvalue()

    def test_format_options_aliases_and_default_dispatch(self):
        for option in ("-f", "--format"):
            for alias in (None, "kubernetes", "k8s", "k", "helm", "h"):
                with self.subTest(option=option, alias=alias), patch(
                    "kubeapp.cli.subprocess.run", return_value=subprocess.CompletedProcess(
                        [], 0, stdout="kind: Deployment\n", stderr="")
                ) as helm:
                    result, output, errors = self.invoke(*([option, alias] if alias else []))
                    self.assertEqual((result, errors), (0, ""))
                    self.assertIn("Deployment", [doc["kind"] for doc in yaml.safe_load_all(output)])
                    self.assertEqual(helm.call_count, int(alias in ("helm", "h")))

    def test_removed_renderer_options_are_rejected(self):
        for option in ("-r", "--renderer"):
            with self.subTest(option=option), self.assertRaises(SystemExit) as raised:
                self.invoke(option, "helm")
            self.assertEqual(raised.exception.code, 2)

    def test_help_remains_reserved(self):
        for option in ("-h", "--help"):
            with self.subTest(option=option), self.assertRaises(SystemExit) as raised:
                self.invoke(option)
            self.assertEqual(raised.exception.code, 0)

    def test_name_override_is_new_validated_model_and_updates_identity(self):
        for option in ("-n", "--name"):
            original = load_application(self.source)
            before = original.model_dump()
            with self.subTest(option=option), patch("kubeapp.cli.load_application", return_value=original), patch(
                "kubeapp.cli.KubernetesRenderer.render", wraps=KubernetesRenderer().render
            ) as render:
                result, output, errors = self.invoke(option, "replacement")
            self.assertEqual((result, errors), (0, ""))
            self.assertIsNot(render.call_args.args[0], original)
            self.assertEqual(original.model_dump(), before)
            documents = list(yaml.safe_load_all(output))
            resources = {doc["kind"]: doc for doc in documents}
            for kind in ("Deployment", "Service"):
                self.assertEqual(resources[kind]["metadata"]["name"], "replacement")
            for document in documents:
                self.assertEqual(document["metadata"]["labels"]["app.kubernetes.io/name"], "replacement")
            deployment = resources["Deployment"]["spec"]
            labels = {"app.kubernetes.io/name": "replacement"}
            self.assertEqual(deployment["selector"]["matchLabels"], labels)
            self.assertEqual(deployment["template"]["metadata"]["labels"], labels)
            self.assertEqual(resources["Service"]["spec"]["selector"], labels)
            pod = deployment["template"]["spec"]
            self.assertEqual(pod["containers"][0]["name"], "web")
            self.assertEqual(pod["initContainers"][0]["name"], "prepare")
            self.assertEqual(pod["serviceAccountName"], "explicit-account")
            self.assertEqual(resources["ConfigMap"]["metadata"]["name"], "explicit-config")
            self.assertEqual(resources["Secret"]["metadata"]["name"], "explicit-secret")
            self.assertEqual(resources["PersistentVolumeClaim"]["metadata"]["name"], "replacement-data")
            self.assertEqual(pod["volumes"][0]["persistentVolumeClaim"]["claimName"], "replacement-data")

    def test_name_reaches_helm_without_changing_execution(self):
        with patch("kubeapp.cli.subprocess.run", return_value=subprocess.CompletedProcess(
            [], 0, stdout="kind: Deployment\n", stderr=""
        )) as helm:
            self.assertEqual(self.invoke("-f", "helm", "-n", "replacement"), (0, "kind: Deployment\n", ""))
        self.assertEqual(helm.call_args.args[0][:3], ["helm", "template", "kube-app"])
        values = yaml.safe_load(helm.call_args.kwargs["input"])
        self.assertEqual(values["name"], "replacement")
        self.assertEqual(values["containerName"], "web")
        self.assertEqual(values["initContainers"][0]["containerName"], "prepare")
        self.assertEqual(values["configuration"][0]["name"], "explicit-config")
        self.assertEqual(values["secrets"][0]["name"], "explicit-secret")
        self.assertEqual(values["serviceAccount"]["name"], "explicit-account")
        self.assertEqual(values["volumes"][0]["persistentVolumeClaim"]["claimName"], "replacement-data")

    def test_invalid_names_preserve_existing_output(self):
        destination = self.base / "existing.yaml"
        for option in ("-n", "--name"):
            for name in ("", "Invalid", "bad_name", "a" * 64):
                with self.subTest(option=option, name=name):
                    destination.write_bytes(b"existing\n")
                    result, output, errors = self.invoke(option, name, "-o", str(destination))
                    self.assertEqual((result, output), (1, ""))
                    self.assertIn("Validation failed:", errors)
                    self.assertIn("name:", errors)
                    self.assertEqual(destination.read_bytes(), b"existing\n")

    def test_output_options_preserve_stdout_content_and_default_name(self):
        for backend in ("kubernetes", "helm"):
            with self.subTest(backend=backend), patch("kubeapp.cli.subprocess.run", return_value=subprocess.CompletedProcess(
                [], 0, stdout="kind: Deployment\nmetadata:\n  name: original\n", stderr=""
            )):
                result, output, errors = self.invoke("-f", backend)
                self.assertEqual((result, errors), (0, ""))
                deployment = next(doc for doc in yaml.safe_load_all(output) if doc["kind"] == "Deployment")
                self.assertEqual(deployment["metadata"]["name"], "original")
                for option in ("-o", "--output"):
                    destination = self.base / backend / option / "output.yaml"
                    self.assertEqual(self.invoke("-f", backend, option, str(destination)), (0, "", ""))
                    self.assertEqual(destination.read_text(encoding="utf-8"), output)
                    destination.write_text("existing", encoding="utf-8")
                    self.assertEqual(self.invoke("-f", backend, option, str(destination)), (0, "", ""))
                    self.assertEqual(destination.read_text(encoding="utf-8"), output)


class RenderCommandTests(unittest.TestCase):
    def setUp(self):
        self.chart = temporary_chart(self)

    def test_format_option_aliases_are_canonical(self):
        parser = build_parser()
        self.assertEqual(parser.parse_args(["render", "app.yaml"]).renderer, "kubernetes")
        for option in ("--format", "-f"):
            for alias, canonical in (("kubernetes", "kubernetes"), ("k8s", "kubernetes"),
                                     ("k", "kubernetes"), ("helm", "helm"), ("h", "helm")):
                with self.subTest(option=option, alias=alias):
                    self.assertEqual(parser.parse_args(["render", "app.yaml", option, alias]).renderer, canonical)

    def test_format_aliases_dispatch_and_output_final_yaml(self):
        source = PROJECT_ROOT / "examples/basic/app.yaml"
        for alias in (None, "kubernetes", "k8s", "k", "helm", "h"):
            with self.subTest(alias=alias):
                argv = ["kube-app", "render", str(source)]
                if alias:
                    argv += ["-f", alias]
                if alias in ("helm", "h"):
                    argv += ["--chart", str(self.chart)]
                output = io.StringIO()
                with (
                    patch.object(sys, "argv", argv), redirect_stdout(output),
                    patch("kubeapp.cli.subprocess.run", return_value=subprocess.CompletedProcess(
                        [], 0, stdout="kind: Deployment\n", stderr="")) as helm,
                ):
                    self.assertEqual(main(), 0)
                documents = list(yaml.safe_load_all(output.getvalue()))
                self.assertEqual(documents[0]["kind"], "Deployment")
                self.assertEqual(helm.call_count, int(alias in ("helm", "h")))
                if helm.called:
                    self.assertEqual(helm.call_args.args[0][:3], ["helm", "template", "kube-app"])
                    self.assertEqual(yaml.safe_load(helm.call_args.kwargs["input"])["name"], "hello-world")

    def test_invalid_format_is_usage_error(self):
        output, errors = io.StringIO(), io.StringIO()
        with (patch.object(sys, "argv", ["kube-app", "render", "app.yaml", "-f", "invalid"]),
              redirect_stdout(output), redirect_stderr(errors)):
            with self.assertRaises(SystemExit) as raised:
                main()
        self.assertEqual(raised.exception.code, 2)
        self.assertEqual(output.getvalue(), "")
        self.assertIn("format must be", errors.getvalue())

    @unittest.skipUnless(shutil.which("helm"), "Helm is required")
    def test_helm_resolves_file_inputs_from_application_directory(self):
        source = PROJECT_ROOT / "examples/advanced/app.yaml"
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, "-m", "kubeapp", "render", str(source), "--format", "helm",
                 "--chart", str(self.chart)],
                cwd=directory, capture_output=True, text=True, timeout=30,
                env={**os.environ, "CATALOG_API_KEY": "cli-example-key",
                     "PYTHONPATH": str(PROJECT_ROOT / "src")},
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        documents = list(yaml.safe_load_all(result.stdout))
        self.assertEqual(len(documents), 7)
        resources = {(doc["kind"], doc["metadata"]["name"]): doc for doc in documents}
        self.assertTrue(resources["ConfigMap", "catalog-config"]["data"])
        self.assertTrue(resources["Secret", "catalog-db"]["stringData"])
        self.assertEqual(resources["Secret", "catalog-api"]["stringData"], {"API_KEY": "cli-example-key"})

    def test_helm_failure_preserves_output_and_returns_render_error(self):
        for failure in (FileNotFoundError("helm not found"), subprocess.TimeoutExpired("helm", 30),
                        subprocess.CompletedProcess([], 1, stdout="partial", stderr="template failed")):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                destination = Path(directory) / "output.yaml"
                destination.write_text("existing")
                output, errors = io.StringIO(), io.StringIO()
                options = {"side_effect": failure} if isinstance(failure, Exception) else {"return_value": failure}
                with (
                    patch.object(sys, "argv", ["kube-app", "render", str(PROJECT_ROOT / "examples/basic/app.yaml"),
                                               "-f", "h", "--chart", str(self.chart), "-o", str(destination)]),
                    patch("kubeapp.cli.subprocess.run", **options),
                    redirect_stdout(output), redirect_stderr(errors),
                ):
                    self.assertEqual(main(), 1)
                self.assertEqual(output.getvalue(), "")
                self.assertEqual(destination.read_text(), "existing")
                self.assertIn("Render failed:", errors.getvalue())

    def test_render_outputs_kubernetes_manifests(self) -> None:
        application_file = (
            PROJECT_ROOT / "examples" / "basic" / "app.yaml"
        )
        output = io.StringIO()

        with patch.object(sys, "argv", ["kube-app", "render", str(application_file)]):
            with redirect_stdout(output):
                exit_code = main()

        self.assertEqual(exit_code, 0)
        deployment, service = yaml.safe_load_all(output.getvalue())
        self.assertEqual(deployment["kind"], "Deployment")
        self.assertEqual(deployment["spec"]["replicas"], 2)
        self.assertEqual(service["spec"]["ports"][0]["port"], 80)

    def test_output_file_matches_stdout(self):
        source = PROJECT_ROOT / "examples/medium/app.yaml"
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "output/medium.yaml"
            output = io.StringIO()
            with (
                patch.object(
                    sys,
                    "argv",
                    ["kube-app", "render", str(source), "-o", str(destination)],
                ),
                redirect_stdout(output),
            ):
                self.assertEqual(main(), 0)
            self.assertEqual(output.getvalue(), "")
            with (
                patch.object(sys, "argv", ["kube-app", "render", str(source)]),
                redirect_stdout(output),
            ):
                self.assertEqual(main(), 0)
            self.assertEqual(destination.read_text(), output.getvalue())

    def test_missing_application_reports_error(self):
        errors = io.StringIO()
        with (
            patch.object(sys, "argv", ["kube-app", "render", "missing.yaml"]),
            redirect_stderr(errors),
        ):
            self.assertEqual(main(), 1)
        self.assertIn("does not exist", errors.getvalue())

    def test_failed_render_preserves_output_and_hides_secret_values(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            data = yaml.safe_load((PROJECT_ROOT / "examples/medium/app.yaml").read_text())
            data["secrets"][0]["data"]["DB_PASSWORD"] = {
                "invalid": "private-value"
            }
            source, output = base / "app.yaml", base / "output.yaml"
            source.write_text(yaml.safe_dump(data))
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
