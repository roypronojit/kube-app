"""Shared fixtures and builders for this test domain."""

from pathlib import Path

import yaml

from kubeapp.manifests import application_to_kubernetes_manifests
from kubeapp.models import Application as IntentApplication
from kubeapp.models import LegacyApplication as Application

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def init_container_application(count=2) -> IntentApplication:
    data = multiple_container_application().model_dump(by_alias=True, exclude_none=True)
    data["init"] = [
        {
            "name": "prepare", "image": "prepare:1", "imagePullPolicy": "Always",
            "environment": {"TASK": "prepare"},
            "configuration": [{"name": "data", "as": "environment"}],
            "secrets": [{"name": "data", "as": "environment"}],
            "resources": {"cpu": {"min": "50m"}},
            "mounts": [{"storage": "data", "path": "/init/data"},
                       {"configuration": "data", "path": "/init/config"}],
        },
        {
            "name": "verify", "image": "verify:2", "imagePullPolicy": "Never",
            "environment": {"TASK": "verify"},
            "resources": {"memory": {"max": "64Mi"}},
            "mounts": [{"secret": "data", "path": "/verify/secret"},
                       {"storage": "data", "path": "/verify/data"}],
        },
    ][:count]
    return IntentApplication.model_validate(data)


def multiple_container_application() -> IntentApplication:
    data = mounted_application().model_dump(by_alias=True, exclude_none=True)
    primary = data["containers"][0]
    primary.update({
        "ports": [{"name": "http", "port": 8080}],
        "environment": {"ROLE": "primary"},
        "configuration": [{"name": "data", "as": "environment"}],
        "secrets": [{"name": "data", "as": "environment"}],
        "resources": {"cpu": {"min": "100m", "max": "500m"}},
        "health": {"ready": {"path": "/ready", "port": "http"}},
    })
    data["containers"].extend([{
        "name": "metrics", "image": "registry.local/metrics:2", "imagePullPolicy": "Always",
        "ports": [{"name": "metrics", "port": 9090}],
        "environment": {"ROLE": "metrics"},
        "configuration": [{"name": "data", "as": "environment"}],
        "secrets": [{"name": "data", "as": "environment"}],
        "resources": {"memory": {"min": "64Mi", "max": "128Mi"}},
        "mounts": [
            {"storage": "data", "path": "/metrics/data"},
            {"secret": "data", "path": "/metrics/secret"},
            {"configuration": "data", "path": "/metrics/config"},
        ],
        "health": {"live": {"path": "/live", "port": 9090, "periodSeconds": 7}},
    }, {"name": "worker", "image": "worker:3", "imagePullPolicy": "Never"}])
    return IntentApplication.model_validate(data)


def health_application(health: dict) -> IntentApplication:
    return IntentApplication.model_validate({
        "name": "catalog",
        "containers": [{
            "name": "catalog", "image": "catalog:1",
            "ports": [{"name": "http", "port": 8080}],
            "health": health,
        }],
    })


def mounted_application() -> IntentApplication:
    """Same resource name across kinds, repeated sources, and distinct paths."""
    return IntentApplication.model_validate({
        "name": "catalog",
        "configuration": [{"name": "data", "data": {"MODE": "test"}}],
        "secrets": [{"name": "data", "data": {"TOKEN": "example"}}],
        "storage": {"name": "data", "size": "10Gi"},
        "containers": [{
            "name": "catalog", "image": "catalog:1",
            "mounts": [
                {"secret": "data", "path": "/etc/secrets"},
                {"storage": "data", "path": "/data"},
                {"configuration": "data", "path": "/etc/config"},
                {"configuration": "data", "path": "/etc/config-copy"},
                {"secret": "data", "path": "/etc/secrets-copy"},
                {"storage": "data", "path": "/data-copy"},
            ],
        }],
    })


def inline_secret_application() -> IntentApplication:
    """Focused configuration/Secret input with demonstration data only."""
    return IntentApplication.model_validate({
        "name": "catalog",
        "configuration": [{"name": "catalog-config", "data": {"APP_ENV": "test"}}],
        "secrets": [
            {"name": "z-db", "data": {
                "PASSWORD": "prefix-${HELM_TEST_PASSWORD}", "PORT": 5432,
                "ENABLED": False, "MULTILINE": "first\nsecond\n",
                "LITERAL": "{{ .Release.Name }}", "EMPTY": "",
            }},
            {"name": "a-api", "data": {"TOKEN": "demonstration-token"}},
            {"name": "unused-secret", "data": {}},
        ],
        "containers": [{
            "name": "catalog", "image": "catalog:1",
            "configuration": [{"name": "catalog-config", "as": "environment"}],
            "secrets": [
                {"name": "a-api", "as": "environment"},
                {"name": "z-db", "as": "environment"},
            ],
        }],
    })


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
