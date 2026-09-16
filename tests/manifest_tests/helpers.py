"""Shared fixtures and builders for this test domain."""

from pathlib import Path

import yaml

from kubeapp.manifests import application_to_kubernetes_manifests
from kubeapp.models import Application as IntentApplication
from kubeapp.models import LegacyApplication as Application

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _example(name: str) -> Application:
    return IntentApplication.model_validate(
        yaml.safe_load((PROJECT_ROOT / "examples" / name).read_text(encoding="utf-8"))
    )


def _output(name: str) -> list[dict[str, object]]:
    return list(
        yaml.safe_load_all(
            (PROJECT_ROOT / "examples" / name).read_text(encoding="utf-8")
        )
    )


def _manifests(
    name: str = "catalog",
    **spec_fields: object,
) -> list[dict[str, object]]:
    return application_to_kubernetes_manifests(
        Application.model_validate(
            {
                "apiVersion": "kubeapp.dev/v1alpha1",
                "kind": "Application",
                "metadata": {"name": name},
                "spec": dict(spec_fields),
            }
        )
    )


def _single_container_manifests(
    **container_fields: object,
) -> list[dict[str, object]]:
    container = {"name": "app", "image": "app:1.0"}
    container.update(container_fields)

    return _manifests(containers=[container], service={"port": 8080})


def _storage_manifests(
    storage: list[dict[str, object]],
) -> list[dict[str, object]]:
    mounts = [
        {
            "name": entry["name"],
            "storage": entry["name"],
            "path": f"/{entry['name']}",
        }
        for entry in storage
    ]

    return _manifests(
        containers=[{"name": "app", "image": "app:1.0", "mounts": mounts}],
        storage=storage,
        service={"port": 8080},
    )


def _deployment(manifests: list[dict[str, object]]) -> dict[str, object]:
    return next(manifest for manifest in manifests if manifest["kind"] == "Deployment")


def _service(manifests: list[dict[str, object]]) -> dict[str, object]:
    return next(manifest for manifest in manifests if manifest["kind"] == "Service")


def _pod_spec(manifests: list[dict[str, object]]) -> dict[str, object]:
    return _deployment(manifests)["spec"]["template"]["spec"]


def _container(manifests: list[dict[str, object]]) -> dict[str, object]:
    return _pod_spec(manifests)["containers"][0]
