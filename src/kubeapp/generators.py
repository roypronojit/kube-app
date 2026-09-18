"""Legacy-schema compatibility; new Helm translation lives in renderers.helm."""

from typing import Any

from kubeapp.models import LegacyApplication as Application
from kubeapp.renderers.helm import _split_image_reference as _split_image_reference


def application_to_helm_values(application: Application) -> dict[str, Any]:
    if application.spec.image is None:
        raise ValueError(
            "Helm values generation supports only the single 'image' form; "
            "use the Kubernetes renderer for applications that define "
            "containers"
        )

    repository, tag = _split_image_reference(application.spec.image)

    values: dict[str, Any] = {
        "name": application.metadata.name,
        "image": {
            "repository": repository,
            "tag": tag,
        },
    }

    if application.spec.service is not None:
        values["service"] = {
            "port": application.spec.service.port,
        }

    if application.spec.resources is not None:
        values["resources"] = application.spec.resources.model_dump(
            exclude_none=True,
        )

    if application.spec.scaling is not None:
        values["scaling"] = {
            "minReplicas": application.spec.scaling.min_replicas,
            "maxReplicas": application.spec.scaling.max_replicas,
        }

    return values
