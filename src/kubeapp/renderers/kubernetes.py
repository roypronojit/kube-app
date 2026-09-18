"""Adapter for the existing Kubernetes manifest implementation."""

from pathlib import Path
from typing import Any

from kubeapp.manifests import application_to_kubernetes_manifests
from kubeapp.models import Application, LegacyApplication


class KubernetesRenderer:
    """Render ordered Kubernetes resource dictionaries."""

    def render(
        self,
        application: Application | LegacyApplication,
        base_dir: str | Path = ".",
    ) -> list[dict[str, Any]]:
        return application_to_kubernetes_manifests(application, base_dir)
