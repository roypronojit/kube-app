import io
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import yaml

from kubeapp.cli import main

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
