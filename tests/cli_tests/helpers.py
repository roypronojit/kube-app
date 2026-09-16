"""Shared CLI fixture locations."""

from pathlib import Path
import tempfile

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def temporary_chart(test):
    directory = tempfile.TemporaryDirectory()
    test.addCleanup(directory.cleanup)
    chart = Path(directory.name)
    (chart / "Chart.yaml").write_text("apiVersion: v2\nname: fixture\nversion: 1.0.0\n")
    return chart
