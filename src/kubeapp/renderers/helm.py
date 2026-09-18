"""Helm values for Basic, inline resource environments, and storage claims.

The kube-app chart consumes these values; Helm execution is left to callers.
"""

import os
import re
from pathlib import Path
from typing import Any

from kubeapp.models import Application, DataResource, IntentContainer
from kubeapp.manifests import SERVICE_PORT_NAME

from .base import Renderer


class HelmRenderer(Renderer[dict[str, Any]]):
    """Translate supported application intent into values, without invoking Helm."""

    def render(
        self, application: Application, base_dir: str | Path = "."
    ) -> dict[str, Any]:
        _validate_supported(application)
        values: dict[str, Any] = {
            "name": application.name,
            "replicaCount": application.replicas,
            "service": {"enabled": False},
            "serviceAccount": {"create": False},
        }
        volumes: dict[tuple[str, str], dict[str, Any]] = {}
        if application.service_account is not None:
            values["serviceAccount"]["name"] = application.service_account
        if application.init:
            values["initContainers"] = [
                _init_container_values(application, container, volumes)
                for container in application.init
            ]
        containers = [
            _container_values(application, container, volumes)
            for container in application.containers
        ]
        if volumes:
            values["volumes"] = list(volumes.values())
        if application.service:
            selected = _service_container(application)
            if not selected.ports:
                rendered = containers[application.containers.index(selected)]
                rendered["ports"] = [{
                    "name": SERVICE_PORT_NAME,
                    "containerPort": application.service.target_port or application.service.port,
                    "protocol": "TCP",
                }]
            values["service"] = {
                "enabled": True,
                "type": application.service.type,
                "port": application.service.port,
                "targetPort": application.service.target_port or (
                    next(p.name for p in selected.ports if p.protocol == "TCP")
                    if selected.ports else SERVICE_PORT_NAME
                ),
            }
        if len(containers) == 1:
            values.update(containers[0])
        else:
            values["containers"] = containers
        for field in ("configuration", "secrets"):
            if getattr(application, field):
                values[field] = [
                    {"name": resource.name, "data": _resource_data(resource, Path(base_dir))}
                    for resource in getattr(application, field)
                ]
        if application.storage is not None:
            values["storage"] = application.storage.model_dump(by_alias=True, exclude_none=True)
        return values


def _init_container_values(
    application: Application, container: IntentContainer,
    volumes: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    """Init containers share resource translation but do not expose ports/probes."""
    values = _container_values(application, container, volumes)
    values.pop("ports")
    return values


def _container_values(
    application: Application, container: IntentContainer,
    volumes: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
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
    }
    if resources:
        values["resources"] = resources
    for field in ("command", "args"):
        value = getattr(container, field)
        if value is not None:
            values[field] = list(value)
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
    if container.environment:
        values["env"] = [
            {"name": name, "value": value}
            for name, value in container.environment.items()
        ]
    if container.mounts:
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


def _service_container(application: Application) -> IntentContainer:
    """Resolve the already validated application-container reference."""
    name = application.service.container or application.containers[0].name
    return next(container for container in application.containers if container.name == name)


def _validate_supported(application: Application) -> None:
    unsupported = []
    for container in application.init:
        if container.ports:
            unsupported.append("init container ports")
    for container in [*application.init, *application.containers]:
        if "@" in container.image:
            unsupported.append("digest image references")
        if len(container.ports) > 1 or any(p.protocol != "TCP" for p in container.ports):
            unsupported.append("ports other than a single TCP port")
    if application.service:
        if application.service.type not in ("ClusterIP", "NodePort", "LoadBalancer"):
            unsupported.append("service.type other than ClusterIP/NodePort/LoadBalancer")
    if unsupported:
        raise NotImplementedError(
            "Helm values support Basic and Medium capabilities; unsupported: "
            + ", ".join(dict.fromkeys(unsupported))
        )


def _resource_data(resource: DataResource, base_dir: Path) -> dict[str, str]:
    """Resolve UTF-8 key=value files and substitutions at render time."""
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
            if not separator or not re.fullmatch(r"[-._a-zA-Z0-9]+", key) or key in data:
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


def _split_image_reference(image: str) -> tuple[str, str]:
    last_slash = image.rfind("/")
    last_colon = image.rfind(":")

    if last_colon > last_slash:
        return image[:last_colon], image[last_colon + 1 :]

    return image, "latest"
