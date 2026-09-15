"""Helm values for Basic capabilities and inline configuration environments.

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
        if application.configuration:
            values["configuration"] = [
                {"name": resource.name, "data": _configuration_data(resource)}
                for resource in application.configuration
            ]
        if container.configuration:
            values["envFrom"] = [
                {"configMapRef": {"name": reference.name}}
                for reference in container.configuration
            ]
        return values


def _validate_supported(application: Application) -> None:
    unsupported = []
    for field in ("init", "secrets", "storage", "service_account"):
        if getattr(application, field):
            unsupported.append(field)
    if len(application.containers) != 1:
        unsupported.append("multiple containers")
    if any(resource.file is not None for resource in application.configuration):
        unsupported.append("file-based configuration")
    for container in application.containers:
        if "@" in container.image:
            unsupported.append("digest image references")
        for field in ("environment", "secrets", "mounts", "health", "command", "args"):
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
            "Helm values support only Basic capabilities and inline configuration "
            "consumed as environment; unsupported: "
            + ", ".join(dict.fromkeys(unsupported))
        )


def _configuration_data(resource: DataResource) -> dict[str, str]:
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
