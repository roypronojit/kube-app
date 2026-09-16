"""Shared renderer names and legacy container selection."""

from typing import Optional

from kubeapp.models import ContainerSpec, LegacyApplication

Labels = dict[str, str]

#: Name given to the container port the Service targets.
SERVICE_PORT_NAME = "http"


def persistent_volume_claim_name(
    application_name: str,
    storage_name: str,
) -> str:
    """Deterministic name of the claim generated for a storage entry."""

    return f"{application_name}-{storage_name}"


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
