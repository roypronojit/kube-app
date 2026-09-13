from typing import Any

from kubeapp.models import Application


def application_to_kubernetes_manifests(
    application: Application,
) -> list[dict[str, Any]]:
    labels = {"app.kubernetes.io/name": application.metadata.name}
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

    if application.spec.resources is not None:
        container["resources"] = application.spec.resources.model_dump(
            exclude_none=True,
        )

    replicas = 1
    if application.spec.scaling is not None:
        replicas = application.spec.scaling.min_replicas

    deployment = {
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
                "spec": {"containers": [container]},
            },
        },
    }

    manifests = [deployment]

    if application.spec.service is not None:
        manifests.append(
            {
                "apiVersion": "v1",
                "kind": "Service",
                "metadata": {
                    "name": application.metadata.name,
                    "labels": labels,
                },
                "spec": {
                    "type": "ClusterIP",
                    "ports": [
                        {
                            "name": "http",
                            "port": application.spec.service.port,
                            "targetPort": "http",
                            "protocol": "TCP",
                        }
                    ],
                    "selector": labels,
                },
            }
        )

    return manifests
