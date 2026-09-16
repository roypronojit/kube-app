"""Application and legacy container specs, environments, and mounts."""

from typing import Any, Optional

from kubeapp.models import Application, ContainerSpec, IntentContainer

from .common import SERVICE_PORT_NAME, persistent_volume_claim_name


def _intent_container(
    container: IntentContainer,
    application: Application,
    volumes: dict[tuple[str, str], dict[str, Any]],
    target: Optional[str],
    is_init: bool = False,
) -> dict[str, Any]:
    result: dict[str, Any] = {"name": container.name, "image": container.image}
    result["imagePullPolicy"] = container.image_pull_policy
    for field in ("command", "args"):
        value = getattr(container, field)
        if value is not None:
            result[field] = list(value)
    if container.health:
        for name in ("readiness", "liveness", "startup"):
            probe = getattr(container.health, name)
            if probe is not None:
                result[f"{name}Probe"] = {
                    "httpGet": {"path": probe.path, "port": probe.port},
                    **probe.model_dump(by_alias=True, exclude={"path", "port"}),
                }
    if container.ports:
        result["ports"] = [
            {"name": p.name, "containerPort": p.port, "protocol": p.protocol}
            for p in container.ports
        ]
    elif not is_init and container.name == target:
        result["ports"] = [
            {
                "name": SERVICE_PORT_NAME,
                "containerPort": application.service.target_port
                or application.service.port,
                "protocol": "TCP",
            }
        ]
    if container.environment:
        result["env"] = [
            {"name": k, "value": v} for k, v in container.environment.items()
        ]
    env_from = [{"configMapRef": {"name": r.name}} for r in container.configuration]
    env_from += [{"secretRef": {"name": r.name}} for r in container.secrets]
    if env_from:
        result["envFrom"] = env_from
    if container.resources:
        resources = {}
        for field, key in (("min", "requests"), ("max", "limits")):
            values = {}
            for name in ("cpu", "memory"):
                bounds = getattr(container.resources, name)
                if bounds is not None and getattr(bounds, field) is not None:
                    values[name] = getattr(bounds, field)
            if values:
                resources[key] = values
        if resources:
            result["resources"] = resources
    for mount in container.mounts:
        kind, name = mount.source
        if mount.source not in volumes:
            # Generated names avoid collisions between resource kinds and long names.
            volume = {"name": f"volume-{len(volumes)}"}
            if kind == "configuration":
                volume["configMap"] = {"name": name}
            elif kind == "secret":
                volume["secret"] = {"secretName": name}
            else:
                volume["persistentVolumeClaim"] = {
                    "claimName": persistent_volume_claim_name(application.name, name)
                }
            volumes[mount.source] = volume
        rendered_mount = {
            "name": volumes[mount.source]["name"],
            "mountPath": mount.path,
        }
        if kind != "storage":
            rendered_mount["readOnly"] = True
        result.setdefault("volumeMounts", []).append(rendered_mount)
    return result


def _container(
    container: ContainerSpec,
    port: Optional[int] = None,
) -> dict[str, Any]:
    rendered: dict[str, Any] = {
        "name": container.name,
        "image": container.image,
    }

    if port is not None:
        rendered["ports"] = [
            {
                "name": SERVICE_PORT_NAME,
                "containerPort": port,
                "protocol": "TCP",
            }
        ]

    environment = _container_environment(container)
    if environment:
        rendered["env"] = environment

    if container.resources is not None:
        rendered["resources"] = container.resources.model_dump(
            exclude_none=True,
        )

    if container.mounts:
        rendered["volumeMounts"] = [
            {"name": mount.name, "mountPath": mount.path} for mount in container.mounts
        ]

    return rendered


def _container_environment(
    container: ContainerSpec,
) -> list[dict[str, Any]]:
    environment: list[dict[str, Any]] = []

    for variable in container.environment:
        if variable.value is not None:
            environment.append({"name": variable.name, "value": variable.value})

        elif variable.secret is not None:
            environment.append(
                {
                    "name": variable.name,
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": variable.secret.name,
                            "key": variable.secret.key,
                        }
                    },
                }
            )

        elif variable.config is not None:
            environment.append(
                {
                    "name": variable.name,
                    "valueFrom": {
                        "configMapKeyRef": {
                            "name": variable.config.name,
                            "key": variable.config.key,
                        }
                    },
                }
            )

        else:
            raise ValueError(f"environment variable '{variable.name}' has no source")

    return environment
