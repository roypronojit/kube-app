import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from kubeapp.cli import main


class RenderCommandTests(unittest.TestCase):
    def test_render_outputs_helm_values(self) -> None:
        application_file = (
            Path(__file__).resolve().parents[1] / "examples" / "basic.yaml"
        )
        output = io.StringIO()

        with patch.object(sys, "argv", ["kube-app", "render", str(application_file)]):
            with redirect_stdout(output):
                exit_code = main()

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            output.getvalue(),
            "name: hello-world\n"
            "image:\n"
            "  repository: nginx\n"
            "  tag: '1.27'\n"
            "service:\n"
            "  port: 80\n"
            "resources:\n"
            "  requests:\n"
            "    cpu: 100m\n"
            "    memory: 128Mi\n"
            "  limits:\n"
            "    cpu: 500m\n"
            "    memory: 256Mi\n"
            "scaling:\n"
            "  minReplicas: 2\n"
            "  maxReplicas: 5\n",
        )
