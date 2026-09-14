import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import yaml

from kubeapp.cli import main


class RenderCommandTests(unittest.TestCase):
    def test_render_outputs_kubernetes_manifests(self) -> None:
        application_file = (
            Path(__file__).resolve().parents[1] / "examples" / "basic" / "app.yaml"
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
        source = Path(__file__).resolve().parents[1] / "examples/medium/app.yaml"
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
