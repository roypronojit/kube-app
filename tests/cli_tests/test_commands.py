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

from .helpers import PROJECT_ROOT


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


class RenderCommandTests(unittest.TestCase):
    def test_renderer_option_aliases_are_canonical(self):
        parser = build_parser()
        self.assertEqual(parser.parse_args(["render", "app.yaml"]).renderer, "kubernetes")
        for option in ("--renderer", "-r"):
            for alias, canonical in (("kubernetes", "kubernetes"), ("k8s", "kubernetes"),
                                     ("k", "kubernetes"), ("helm", "helm"), ("h", "helm")):
                with self.subTest(option=option, alias=alias):
                    self.assertEqual(parser.parse_args(["render", "app.yaml", option, alias]).renderer, canonical)

    def test_renderer_aliases_dispatch_and_output_final_yaml(self):
        source = PROJECT_ROOT / "examples/basic/app.yaml"
        for alias in (None, "kubernetes", "k8s", "k", "helm", "h"):
            with self.subTest(alias=alias):
                argv = ["kube-app", "render", str(source)]
                if alias:
                    argv += ["-r", alias]
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

    def test_invalid_renderer_is_usage_error(self):
        output, errors = io.StringIO(), io.StringIO()
        with (patch.object(sys, "argv", ["kube-app", "render", "app.yaml", "-r", "invalid"]),
              redirect_stdout(output), redirect_stderr(errors)):
            with self.assertRaises(SystemExit) as raised:
                main()
        self.assertEqual(raised.exception.code, 2)
        self.assertEqual(output.getvalue(), "")
        self.assertIn("renderer must be", errors.getvalue())

    @unittest.skipUnless(shutil.which("helm"), "Helm is required")
    def test_helm_resolves_file_inputs_from_application_directory(self):
        source = PROJECT_ROOT / "examples/advanced/app.yaml"
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, "-m", "kubeapp", "render", str(source), "--renderer", "helm"],
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
                                               "-r", "h", "-o", str(destination)]),
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
