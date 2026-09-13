from typing import Any

from kubeapp.models import (
    Application,
    ApplicationSpec,
    ServiceSpec,
    StorageSpec,
)

Labels = dict[str, str]

#: Access mode used for all kube-app managed storage. Application
#: developers do not choose this; the platform does.
DEFAULT_ACCESS_MODES = ["ReadWriteOnce"]


def persistent_volume_claim_name(
    application_name: str,
    storage_name: str,
) -> str:
    """Deterministic name of the claim generated for a storage entry."""

    return f"{application_name}-{storage_name}"


def application_to_kubernetes_manifests(
    application: Application,
) -> list[dict[str, Any]]:
    labels = {"app.kubernetes.io/name": application.metadata.name}

    manifests: list[dict[str, Any]] = [
        _persistent_volume_claim(
            application.metadata.name,
            storage_name,
            storage,
            labels,
        )
        for storage_name, storage in application.spec.storage.items()
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


def _deployment(
    application: Application,
    labels: Labels,
) -> dict[str, Any]:
    pod_spec: dict[str, Any] = {
        "containers": [_container(application)],
    }

    volumes = _pod_volumes(application)
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


def _container(application: Application) -> dict[str, Any]:
    container: dict[str, Any] = {
        "name": application.metadata.name,
        "image": application.spec.image,
    }

    if application.spec.service is not None:
        container["ports"] = [
            {
                "name": "http",
                "containerPort": application.spec.service.port,
                "protocol": "TCP",
            }
        ]

    environment = _container_environment(application.spec)
    if environment:
        container["env"] = environment

    if application.spec.resources is not None:
        container["resources"] = application.spec.resources.model_dump(
            exclude_none=True,
        )

    volume_mounts = _volume_mounts(application.spec)
    if volume_mounts:
        container["volumeMounts"] = volume_mounts

    return container


def _container_environment(spec: ApplicationSpec) -> list[dict[str, Any]]:
    """Translate application configuration into container environment.

    A provided value is looked up under the key that matches the
    environment-variable name, so the application only has to know the name
    of the provider it was given.
    """

    environment: list[dict[str, Any]] = [
        {"name": name, "value": value}
        for name, value in spec.environment.items()
    ]

    environment.extend(
        {
            "name": name,
            "valueFrom": {
                "secretKeyRef": {"name": provider, "key": name},
            },
        }
        for name, provider in spec.secrets.items()
    )

    environment.extend(
        {
            "name": name,
            "valueFrom": {
                "configMapKeyRef": {"name": provider, "key": name},
            },
        }
        for name, provider in spec.configuration.items()
    )

    return environment


def _pod_volumes(application: Application) -> list[dict[str, Any]]:
    return [
        {
            "name": storage_name,
            "persistentVolumeClaim": {
                "claimName": persistent_volume_claim_name(
                    application.metadata.name,
                    storage_name,
                ),
            },
        }
        for storage_name in application.spec.storage
    ]


def _volume_mounts(spec: ApplicationSpec) -> list[dict[str, Any]]:
    return [
        {"name": storage_name, "mountPath": storage.path}
        for storage_name, storage in spec.storage.items()
    ]


def _persistent_volume_claim(
    application_name: str,
    storage_name: str,
    storage: StorageSpec,
    labels: Labels,
) -> dict[str, Any]:
    return {
        "apiVersion": "v1",
        "kind": "PersistentVolumeClaim",
        "metadata": {
            "name": persistent_volume_claim_name(
                application_name,
                storage_name,
            ),
            "labels": labels,
        },
        "spec": {
            "accessModes": list(DEFAULT_ACCESS_MODES),
            "resources": {"requests": {"storage": storage.size}},
        },
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
            "type": "ClusterIP",
            "ports": [
                {
                    "name": "http",
                    "port": service.port,
                    "targetPort": "http",
                    "protocol": "TCP",
                }
            ],
            "selector": labels,
        },
    }
