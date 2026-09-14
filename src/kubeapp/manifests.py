import os
import re
from pathlib import Path
from typing import Any, Optional

from kubeapp.models import (
    Application,
    ContainerSpec,
    DataResource,
    IntentContainer,
    LegacyApplication,
    MountSpec,
    ServiceSpec,
    StorageSpec,
)

Labels = dict[str, str]

#: Name given to the container port the Service targets.
SERVICE_PORT_NAME = "http"


def persistent_volume_claim_name(
    application_name: str,
    storage_name: str,
) -> str:
    """Deterministic name of the claim generated for a storage entry."""

    return f"{application_name}-{storage_name}"


def application_to_kubernetes_manifests(
    application: Application | LegacyApplication,
    base_dir: str | Path = ".",
) -> list[dict[str, Any]]:
    if isinstance(application, Application):
        return _intent_manifests(application, Path(base_dir))

    labels = {"app.kubernetes.io/name": application.metadata.name}

    manifests: list[dict[str, Any]] = [
        _persistent_volume_claim(
            application.metadata.name,
            storage,
            labels,
        )
        for storage in application.spec.storage
    ]

    manifests.append(_deployment(application, labels))

    if application.spec.service is not None:
        manifests.append(
            _service(
                application.metadata.name,
                application.spec.service,
                labels,
            )
        )

    return manifests


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


def _intent_manifests(application: Application, base_dir: Path) -> list[dict[str, Any]]:
    labels = {"app.kubernetes.io/name": application.name}
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
    if application.storage:
        manifests.append(
            _persistent_volume_claim(application.name, application.storage, labels)
        )

    volumes: dict[tuple[str, str], dict[str, Any]] = {}
    target = None
    if application.service:
        target = application.service.container or application.containers[0].name

    def render_container(
        container: IntentContainer, is_init: bool = False
    ) -> dict[str, Any]:
        result: dict[str, Any] = {"name": container.name, "image": container.image}
        if not is_init and container.name == target:
            result["ports"] = [
                {
                    "name": SERVICE_PORT_NAME,
                    "containerPort": application.service.port,
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
                        "claimName": persistent_volume_claim_name(
                            application.name, name
                        )
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

    pod: dict[str, Any] = {}
    if application.service_account:
        pod["serviceAccountName"] = application.service_account
    if application.init:
        pod["initContainers"] = [render_container(c, True) for c in application.init]
    pod["containers"] = [render_container(c) for c in application.containers]
    if volumes:
        pod["volumes"] = list(volumes.values())
    manifests.append(
        {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": application.name, "labels": labels},
            "spec": {
                "replicas": application.replicas,
                "selector": {"matchLabels": dict(labels)},
                "template": {"metadata": {"labels": dict(labels)}, "spec": pod},
            },
        }
    )
    if application.service:
        manifests.append(_service(application.name, application.service, labels))
    return manifests


def application_containers(application: LegacyApplication) -> list[ContainerSpec]:
    """Containers of the application, resolving the single-image shorthand."""

    if application.spec.containers:
        return list(application.spec.containers)

    return [
        ContainerSpec(
            name=application.metadata.name,
            image=application.spec.image,
            resources=application.spec.resources,
        )
    ]


def service_target_container(application: LegacyApplication) -> Optional[str]:
    """Container the Service sends traffic to, if the application has one."""

    if application.spec.service is None:
        return None

    if application.spec.service.container is not None:
        return application.spec.service.container

    return application_containers(application)[0].name


def _deployment(
    application: LegacyApplication,
    labels: Labels,
) -> dict[str, Any]:
    containers = application_containers(application)
    target = service_target_container(application)
    service_port = None
    if application.spec.service is not None:
        service_port = application.spec.service.port

    pod_spec: dict[str, Any] = {}

    if application.spec.service_account is not None:
        pod_spec["serviceAccountName"] = application.spec.service_account.name

    if application.spec.init_containers:
        pod_spec["initContainers"] = [
            _container(container) for container in application.spec.init_containers
        ]

    pod_spec["containers"] = [
        _container(
            container,
            port=service_port if container.name == target else None,
        )
        for container in containers
    ]

    volumes = _pod_volumes(
        application.metadata.name,
        [*application.spec.init_containers, *containers],
    )
    if volumes:
        pod_spec["volumes"] = volumes

    replicas = 1
    if application.spec.scaling is not None:
        replicas = application.spec.scaling.min_replicas

    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {
            "name": application.metadata.name,
            "labels": labels,
        },
        "spec": {
            "replicas": replicas,
            "selector": {"matchLabels": labels},
            "template": {
                "metadata": {"labels": labels},
                "spec": pod_spec,
            },
        },
    }


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
