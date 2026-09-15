"""Renderer contract independent of backend output formats."""

from pathlib import Path
from typing import Protocol, TypeVar

from kubeapp.models import Application


Output = TypeVar("Output", covariant=True)


class Renderer(Protocol[Output]):
    """Translate validated application intent into a backend-specific result.

    Resolve file-based inputs relative to base_dir. Serialization and writing
    output belong to the caller. Rendering must not mutate the application.
    """

    def render(
        self, application: Application, base_dir: str | Path = "."
    ) -> Output:
        ...
