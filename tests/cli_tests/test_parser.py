import tempfile
import unittest
from pathlib import Path

from kubeapp.parser import ApplicationParseError, load_application


class ParserErrorTests(unittest.TestCase):
    def test_rejects_non_object_and_invalid_yaml(self):
        for content, message in (
            ("- name: worker\n", "must be a YAML object"),
            ("name: [\n", "Invalid YAML"),
        ):
            with self.subTest(content=content), tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / "app.yaml"
                source.write_text(content, encoding="utf-8")
                with self.assertRaisesRegex(ApplicationParseError, message):
                    load_application(source)

    def test_rejects_directory_and_missing_path(self):
        with tempfile.TemporaryDirectory() as directory:
            for source, message in (
                (Path(directory), "is not a file"),
                (Path(directory) / "missing.yaml", "does not exist"),
            ):
                with self.subTest(source=source):
                    with self.assertRaisesRegex(ApplicationParseError, message):
                        load_application(source)
