"""Kubernetes rendering entry point and backward-compatible helper exports."""

from pathlib import Path
from typing import Any

from kubeapp.models import Application, LegacyApplication

from .common import (
    SERVICE_PORT_NAME as SERVICE_PORT_NAME,
)
from .common import (
    Labels as Labels,
)
from .common import (
    application_containers as application_containers,
)
from .common import (
    persistent_volume_claim_name as persistent_volume_claim_name,
)
from .common import (
    service_target_container as service_target_container,
)
from .containers import _container as _container
from .containers import _container_environment as _container_environment
from .deployment import _deployment, _intent_deployment
from .resources import (
    _configuration_manifests,
    _intent_service,
    _persistent_volume_claim,
    _service,
)
from .resources import (
    _pod_volume as _pod_volume,
)
from .resources import (
    _pod_volumes as _pod_volumes,
)
from .resources import (
    _resource_data as _resource_data,
)


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


def _intent_manifests(application: Application, base_dir: Path) -> list[dict[str, Any]]:
    labels = {"app.kubernetes.io/name": application.name}
    manifests = _configuration_manifests(application, base_dir, labels)
    if application.storage:
        manifests.append(
            _persistent_volume_claim(application.name, application.storage, labels)
        )
    manifests.append(_intent_deployment(application, labels))
    if application.service:
        manifests.append(_intent_service(application, labels))
    return manifests
