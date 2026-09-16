"""ConfigMaps, Secrets, persistent volumes, and Services."""

import os
import re
from pathlib import Path
from typing import Any

from kubeapp.models import (
    Application,
    ContainerSpec,
    DataResource,
    MountSpec,
    ServiceSpec,
    StorageSpec,
)

from .common import SERVICE_PORT_NAME, Labels, persistent_volume_claim_name


def _resource_data(resource: DataResource, base_dir: Path) -> dict[str, str]:
    """Read simple UTF-8 key=value files at render time."""
    data = dict(resource.data or {})
    if resource.file is not None:
        path = base_dir / resource.file
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise ValueError(f"Cannot read resource file '{resource.file}'") from exc
        for number, line in enumerate(content.splitlines(), 1):
            line = line.strip()
            if not line or line.startswith(("#", "!")):
                continue
            key, separator, value = line.partition("=")
            key = key.strip()
            if (
                not separator
                or not re.fullmatch(r"[-._a-zA-Z0-9]+", key)
                or key in data
            ):
                raise ValueError(
                    f"Invalid or duplicate entry in '{resource.file}' at line {number}"
                )
            data[key] = value.strip()

    def substitute(match: re.Match) -> str:
        variable = match[1]
        if variable not in os.environ:
            raise ValueError(
                f"Missing environment variable '{variable}' for resource '{resource.name}'"
            )
        return os.environ[variable]

    return {
        key: re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", substitute, value)
        for key, value in data.items()
    }


def _configuration_manifests(
    application: Application, base_dir: Path, labels: Labels
) -> list[dict[str, Any]]:
    manifests: list[dict[str, Any]] = []
    for kind, resources, data_key in (
        ("ConfigMap", application.configuration, "data"),
        ("Secret", application.secrets, "stringData"),
    ):
        for resource in resources:
            manifest = {
                "apiVersion": "v1",
                "kind": kind,
                "metadata": {"name": resource.name, "labels": labels},
                data_key: _resource_data(resource, base_dir),
            }
            if kind == "Secret":
                manifest["type"] = "Opaque"
            manifests.append(manifest)
    return manifests


def _pod_volumes(
    application_name: str,
    containers: list[ContainerSpec],
) -> list[dict[str, Any]]:
    """One volume per distinct mount name, in first-mounted order."""

    volumes: list[dict[str, Any]] = []
    seen: set[str] = set()

    for container in containers:
        for mount in container.mounts:
            if mount.name in seen:
                continue

            seen.add(mount.name)
            volumes.append(_pod_volume(application_name, mount))

    return volumes


def _pod_volume(
    application_name: str,
    mount: MountSpec,
) -> dict[str, Any]:
    if mount.config is not None:
        return {
            "name": mount.name,
            "configMap": {"name": mount.config.name},
        }

    if mount.secret is not None:
        return {
            "name": mount.name,
            "secret": {"secretName": mount.secret.name},
        }

    if mount.storage is not None:
        return {
            "name": mount.name,
            "persistentVolumeClaim": {
                "claimName": persistent_volume_claim_name(
                    application_name,
                    mount.storage,
                ),
            },
        }

    raise ValueError(f"mount '{mount.name}' has no source")


def _persistent_volume_claim(
    application_name: str,
    storage: StorageSpec,
    labels: Labels,
) -> dict[str, Any]:
    claim_spec: dict[str, Any] = {
        "accessModes": list(storage.access_modes),
    }

    if storage.storage_class is not None:
        claim_spec["storageClassName"] = storage.storage_class

    claim_spec["resources"] = {"requests": {"storage": storage.size}}

    return {
        "apiVersion": "v1",
        "kind": "PersistentVolumeClaim",
        "metadata": {
            "name": persistent_volume_claim_name(
                application_name,
                storage.name,
            ),
            "labels": labels,
        },
        "spec": claim_spec,
    }


def _service(
    name: str,
    service: ServiceSpec,
    labels: Labels,
) -> dict[str, Any]:
    return {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {
            "name": name,
            "labels": labels,
        },
        "spec": {
            "type": service.type,
            "ports": [
                {
                    "name": SERVICE_PORT_NAME,
                    "port": service.port,
                    "targetPort": SERVICE_PORT_NAME,
                    "protocol": "TCP",
                }
            ],
            "selector": dict(labels),
        },
    }


def _intent_service(application: Application, labels: Labels) -> dict[str, Any]:
    target = application.service.container or application.containers[0].name
    service = _service(application.name, application.service, labels)
    target_container = next(c for c in application.containers if c.name == target)
    service["spec"]["ports"][0]["targetPort"] = application.service.target_port or (
        next(p.name for p in target_container.ports if p.protocol == "TCP")
        if target_container.ports
        else SERVICE_PORT_NAME
    )
    return service
