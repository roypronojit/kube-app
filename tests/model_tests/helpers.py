"""Shared fixtures and builders for this test domain."""

from pathlib import Path

import yaml

from kubeapp.models import Application as IntentApplication
from kubeapp.models import LegacyApplication as Application

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _example(name: str) -> Application:
    return IntentApplication.model_validate(
        yaml.safe_load((PROJECT_ROOT / "examples" / name).read_text(encoding="utf-8"))
    )


def _application_data(name: str = "hello-world") -> dict[str, object]:
    return {
        "apiVersion": "kubeapp.dev/v1alpha1",
        "kind": "Application",
        "metadata": {"name": name},
        "spec": {"image": "nginx:1.27"},
    }


def _application(**spec_fields: object) -> Application:
    application_data = _application_data()
    application_data["spec"].update(spec_fields)

    return Application.model_validate(application_data)


def _containers_application(**spec_fields: object) -> Application:
    application_data = _application_data()
    application_data["spec"] = dict(spec_fields)

    return Application.model_validate(application_data)


def _container(**container_fields: object):
    container = {"name": "app", "image": "app:1.0"}
    container.update(container_fields)
    application = _containers_application(containers=[container])

    return application.spec.containers[0]


def _storage_application(storage: list[dict[str, object]]) -> Application:
    mounts = [
        {
            "name": entry["name"],
            "storage": entry["name"],
            "path": f"/{entry['name']}",
        }
        for entry in storage
    ]

    return _containers_application(
        containers=[
            {"name": "app", "image": "app:1.0", "mounts": mounts},
        ],
        storage=storage,
    )
