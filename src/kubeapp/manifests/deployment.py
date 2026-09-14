"""Deployment and pod assembly for both application schemas."""

from typing import Any

from kubeapp.models import Application, LegacyApplication

from .common import Labels, application_containers, service_target_container
from .containers import _container, _intent_container
from .resources import _pod_volumes


def _intent_deployment(application: Application, labels: Labels) -> dict[str, Any]:
    volumes: dict[tuple[str, str], dict[str, Any]] = {}
    target = None
    if application.service:
        target = application.service.container or application.containers[0].name

    pod: dict[str, Any] = {}
    if application.service_account:
        pod["serviceAccountName"] = application.service_account
    if application.init:
        pod["initContainers"] = [
            _intent_container(c, application, volumes, target, True)
            for c in application.init
        ]
    pod["containers"] = [
        _intent_container(c, application, volumes, target)
        for c in application.containers
    ]
    if volumes:
        pod["volumes"] = list(volumes.values())
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": application.name, "labels": labels},
        "spec": {
            "replicas": application.replicas,
            "selector": {"matchLabels": dict(labels)},
            "template": {"metadata": {"labels": dict(labels)}, "spec": pod},
        },
    }


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
