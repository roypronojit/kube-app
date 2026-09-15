"""Helm values for Basic, inline resource environments, and storage claims.

The kube-app chart consumes these values; Helm execution is left to callers.
"""

import os
import re
from pathlib import Path
from typing import Any

from kubeapp.models import Application, DataResource

from .base import Renderer


class HelmRenderer(Renderer[dict[str, Any]]):
    """Translate supported application intent into values, without invoking Helm."""

    def render(
        self, application: Application, base_dir: str | Path = "."
    ) -> dict[str, Any]:
        _validate_supported(application)
        container = application.containers[0]
        repository, tag = _split_image_reference(container.image)
        resources = {}
        if container.resources:
            for bound, key in (("min", "requests"), ("max", "limits")):
                quantities = {}
                for name in ("cpu", "memory"):
                    limits = getattr(container.resources, name)
                    if limits is not None and getattr(limits, bound) is not None:
                        quantities[name] = getattr(limits, bound)
                if quantities:
                    resources[key] = quantities

        values: dict[str, Any] = {
            "name": application.name,
            "replicaCount": application.replicas,
            "containerName": container.name,
            "image": {
                "repository": repository,
                "tag": tag,
                "pullPolicy": container.image_pull_policy,
            },
            "ports": [
                {"name": p.name, "containerPort": p.port, "protocol": p.protocol}
                for p in container.ports
            ],
            "resources": resources,
            "service": {"enabled": False},
            "serviceAccount": {"create": False},
        }
        if application.service:
            values["service"] = {
                "enabled": True,
                "type": application.service.type,
                "port": application.service.port,
                "targetPort": container.ports[0].name,
            }
        for field in ("configuration", "secrets"):
            if getattr(application, field):
                values[field] = [
                    {"name": resource.name, "data": _inline_resource_data(resource)}
                    for resource in getattr(application, field)
                ]
        env_from = [
            {"configMapRef": {"name": reference.name}}
            for reference in container.configuration
        ]
        env_from += [
            {"secretRef": {"name": reference.name}}
            for reference in container.secrets
        ]
        if env_from:
            values["envFrom"] = env_from
        if application.storage is not None:
            values["storage"] = application.storage.model_dump(
                by_alias=True, exclude_none=True
            )
        if container.mounts:
            volumes: dict[tuple[str, str], dict[str, Any]] = {}
            volume_mounts = []
            for mount in container.mounts:
                kind, name = mount.source
                if mount.source not in volumes:
                    volume: dict[str, Any] = {"name": f"volume-{len(volumes)}"}
                    if kind == "configuration":
                        volume["configMap"] = {"name": name}
                    elif kind == "secret":
                        volume["secret"] = {"secretName": name}
                    else:
                        volume["persistentVolumeClaim"] = {
                            "claimName": f"{application.name}-{name}"
                        }
                    volumes[mount.source] = volume
                rendered_mount = {
                    "name": volumes[mount.source]["name"], "mountPath": mount.path,
                }
                if kind != "storage":
                    rendered_mount["readOnly"] = True
                volume_mounts.append(rendered_mount)
            values["volumes"] = list(volumes.values())
            values["volumeMounts"] = volume_mounts
        if container.health:
            for name in ("readiness", "liveness", "startup"):
                probe = getattr(container.health, name)
                if probe is not None:
                    values[f"{name}Probe"] = {
                        "httpGet": {"path": probe.path, "port": probe.port},
                        **probe.model_dump(by_alias=True, exclude={"path", "port"}),
                    }
        return values


def _validate_supported(application: Application) -> None:
    unsupported = []
    for field in ("init", "service_account"):
        if getattr(application, field):
            unsupported.append(field)
    if len(application.containers) != 1:
        unsupported.append("multiple containers")
    if any(resource.file is not None for resource in application.configuration):
        unsupported.append("file-based configuration")
    if any(resource.file is not None for resource in application.secrets):
        unsupported.append("file-based secrets")
    for container in application.containers:
        if "@" in container.image:
            unsupported.append("digest image references")
        for field in ("environment", "command", "args"):
            if getattr(container, field):
                unsupported.append(field)
        if len(container.ports) > 1 or any(p.protocol != "TCP" for p in container.ports):
            unsupported.append("ports other than a single TCP port")
    if application.service:
        if application.service.type != "ClusterIP":
            unsupported.append("service.type other than ClusterIP")
        if application.service.container is not None or application.service.target_port is not None:
            unsupported.append("explicit service container/targetPort")
        if not application.containers[0].ports:
            unsupported.append("service without a declared container port")
    if unsupported:
        raise NotImplementedError(
            "Helm values support only Basic capabilities and inline configuration/secrets "
            "consumed as environment, plus storage claims, resource mounts, and HTTP probes; unsupported: "
            + ", ".join(dict.fromkeys(unsupported))
        )


def _inline_resource_data(resource: DataResource) -> dict[str, str]:
    """Resolve inline substitutions without changing the validated model."""
    def substitute(match: re.Match) -> str:
        variable = match[1]
        if variable not in os.environ:
            raise ValueError(
                f"Missing environment variable '{variable}' for resource '{resource.name}'"
            )
        return os.environ[variable]

    return {
        key: re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", substitute, value)
        for key, value in (resource.data or {}).items()
    }


def _split_image_reference(image: str) -> tuple[str, str]:
    last_slash = image.rfind("/")
    last_colon = image.rfind(":")

    if last_colon > last_slash:
        return image[:last_colon], image[last_colon + 1 :]

    return image, "latest"
