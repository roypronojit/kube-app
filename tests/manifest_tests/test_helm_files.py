"""File input semantics shared by the two rendering paths."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from kubeapp.parser import load_application
from kubeapp.renderers import HelmRenderer, KubernetesRenderer


def file_application(directory):
    source = directory / "app.yaml"
    source.write_text(yaml.safe_dump({
        "name": "catalog",
        "configuration": [{"name": "settings", "file": "inputs/config.properties"}],
        "secrets": [{"name": "credentials", "file": "inputs/secret.env"}],
        "containers": [{"name": "catalog", "image": "catalog:1"}],
    }), encoding="utf-8")
    return load_application(source)


class HelmFileTests(unittest.TestCase):
    def test_relative_files_substitution_and_immutability(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "inputs").mkdir()
            (base / "inputs/config.properties").write_text(
                "# comment\n! comment\n\n MODE = production \nURL=a=b\nEMPTY=\nUSER=${HELM_FILE_USER}\n",
                encoding="utf-8",
            )
            (base / "inputs/secret.env").write_text("TOKEN=${HELM_FILE_USER}\nUNICODE=café\n", encoding="utf-8")
            application = file_application(base)
            before = application.model_dump()
            with patch.dict(os.environ, {"HELM_FILE_USER": "example"}):
                expected = KubernetesRenderer().render(application, base)
                for context in (base, str(base)):
                    values = HelmRenderer().render(application, context)
                    self.assertEqual(values["configuration"], [{"name": "settings", "data": {
                        "MODE": "production", "URL": "a=b", "EMPTY": "", "USER": "example",
                    }}])
                    self.assertEqual(values["secrets"], [{"name": "credentials", "data": {
                        "TOKEN": "example", "UNICODE": "café",
                    }}])
                    self.assertEqual(values["configuration"][0]["data"], expected[0]["data"])
                    self.assertEqual(values["secrets"][0]["data"], expected[1]["stringData"])
            self.assertEqual(application.model_dump(), before)

    def test_file_errors_match_kubernetes_without_mutating_application(self):
        cases = (None, "directory", b'\xff', b'INVALID', b'A=1\nA=2', b'bad key=value', b'A=${HELM_MISSING}')
        for field in ("configuration", "secrets"):
            for content in cases:
                with self.subTest(field=field, content=content), tempfile.TemporaryDirectory() as directory:
                    base = Path(directory)
                    application = file_application(base)
                    # Isolate the file under test using a fresh validated model.
                    data = application.model_dump(by_alias=True)
                    data["secrets" if field == "configuration" else "configuration"] = []
                    application = type(application).model_validate(data)
                    resource = getattr(application, field)[0]
                    path = base / resource.file
                    path.parent.mkdir()
                    if content == "directory":
                        path.mkdir()
                    elif content is not None:
                        path.write_bytes(content)
                    before = application.model_dump()
                    errors = []
                    with patch.dict(os.environ, {}, clear=True):
                        for renderer in (KubernetesRenderer(), HelmRenderer()):
                            with self.assertRaises(ValueError) as raised:
                                renderer.render(application, base)
                            errors.append(str(raised.exception))
                    self.assertEqual(errors[0], errors[1])
                    self.assertEqual(application.model_dump(), before)
