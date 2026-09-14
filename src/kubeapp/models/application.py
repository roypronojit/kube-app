"""Application composition, services, and cross-resource validation."""

from typing import Optional

from pydantic import Field, model_validator

from .common import (
    DNS_LABEL_PATTERN,
    ImageReference,
    LocalName,
    ProviderName,
    ServiceType,
    StrictModel,
    _reject_duplicates,
)
from .configuration import DataResource, StorageSpec
from .container import (
    ContainerSpec,
    IntentContainer,
    PortName,
    PortNumber,
    ResourcesSpec,
)


class ApplicationMetadata(StrictModel):
    name: str = Field(
        min_length=1,
        max_length=63,
        pattern=DNS_LABEL_PATTERN,
    )


class ServiceSpec(StrictModel):
    """How the application is reached by its clients."""

    port: int = Field(gt=0, le=65535)
    type: ServiceType = "ClusterIP"
    container: Optional[LocalName] = None


class ServiceAccountSpec(StrictModel):
    """The identity the application runs as.

    The named service account must already exist. Creating one is a
    deliberate later step.
    """

    name: ProviderName


class ScalingSpec(StrictModel):
    min_replicas: int = Field(default=1, ge=1)
    max_replicas: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def validate_range(self) -> "ScalingSpec":
        if self.min_replicas > self.max_replicas:
            raise ValueError("minReplicas cannot be greater than maxReplicas")

        return self


class ApplicationSpec(StrictModel):
    #: Single-container shorthand. Mutually exclusive with ``containers``.
    image: Optional[ImageReference] = None
    #: Resources for the single-container shorthand.
    resources: Optional[ResourcesSpec] = None

    containers: list[ContainerSpec] = Field(default_factory=list)
    init_containers: list[ContainerSpec] = Field(
        default_factory=list,
        alias="initContainers",
    )
    storage: list[StorageSpec] = Field(default_factory=list)
    service: Optional[ServiceSpec] = None
    service_account: Optional[ServiceAccountSpec] = Field(
        default=None,
        alias="serviceAccount",
    )
    scaling: Optional[ScalingSpec] = None

    @property
    def declared_containers(self) -> list[ContainerSpec]:
        """Containers written down by the developer, init containers first."""

        return [*self.init_containers, *self.containers]

    @model_validator(mode="after")
    def validate_containers(self) -> "ApplicationSpec":
        if self.image is None and not self.containers:
            raise ValueError("spec must define either image or containers")

        if self.image is not None and self.containers:
            raise ValueError(
                "spec cannot define both image and containers; "
                "move the image into a containers entry"
            )

        if self.containers and self.resources is not None:
            raise ValueError(
                "resources must be set on each containers entry instead of on the spec"
            )

        _reject_duplicates(
            [container.name for container in self.declared_containers],
            "container name",
        )

        return self

    @model_validator(mode="after")
    def validate_storage(self) -> "ApplicationSpec":
        _reject_duplicates(
            [storage.name for storage in self.storage],
            "storage name",
        )

        declared = {storage.name for storage in self.storage}
        mounted: set[str] = set()

        for container in self.declared_containers:
            for mount in container.mounts:
                if mount.storage is None:
                    continue

                if mount.storage not in declared:
                    raise ValueError(
                        f"mount '{mount.name}' in container "
                        f"'{container.name}' references undefined storage "
                        f"'{mount.storage}'"
                    )

                mounted.add(mount.storage)

        unmounted = sorted(declared - mounted)
        if unmounted:
            raise ValueError(
                f"storage must be mounted by a container: {', '.join(unmounted)}"
            )

        return self

    @model_validator(mode="after")
    def validate_mounts(self) -> "ApplicationSpec":
        sources: dict[str, tuple[str, str]] = {}

        for container in self.declared_containers:
            for mount in container.mounts:
                known = sources.get(mount.name)

                if known is not None and known != mount.source:
                    raise ValueError(
                        f"mount '{mount.name}' is used for more than one "
                        f"source: {known[0]} '{known[1]}' and "
                        f"{mount.source[0]} '{mount.source[1]}'"
                    )

                sources[mount.name] = mount.source

        return self

    @model_validator(mode="after")
    def validate_service_target(self) -> "ApplicationSpec":
        if self.service is None:
            return self

        names = [container.name for container in self.containers]

        if self.service.container is not None:
            if self.image is not None:
                raise ValueError(
                    "service cannot name a container unless containers are defined"
                )

            if self.service.container not in names:
                raise ValueError(
                    f"service references unknown container '{self.service.container}'"
                )

        elif len(names) > 1:
            raise ValueError(
                "service must name the container that receives traffic "
                "when more than one container is defined"
            )

        return self


class LegacyApplication(StrictModel):
    api_version: str = Field(alias="apiVersion")
    kind: str
    metadata: ApplicationMetadata
    spec: ApplicationSpec

    @model_validator(mode="after")
    def validate_default_container_name(self) -> "LegacyApplication":
        if self.spec.image is None:
            return self

        for container in self.spec.init_containers:
            if container.name == self.metadata.name:
                raise ValueError(
                    f"init container '{container.name}' cannot reuse the "
                    "application name, which the single-container "
                    "shorthand already uses"
                )

        return self

    def validate_application(self) -> None:
        if self.api_version != "kubeapp.dev/v1alpha1":
            raise ValueError(f"Unsupported apiVersion: {self.api_version}")

        if self.kind != "Application":
            raise ValueError(f"Unsupported kind: {self.kind}")


class IntentService(ServiceSpec):
    port: PortNumber
    target_port: Optional[PortNumber | PortName] = Field(
        default=None, alias="targetPort"
    )


class Application(StrictModel):
    """Public application intent, independent of any renderer."""

    name: LocalName
    replicas: int = Field(default=1, ge=0, strict=True)
    containers: list[IntentContainer] = Field(min_length=1)
    init: list[IntentContainer] = Field(default_factory=list)
    configuration: list[DataResource] = Field(default_factory=list)
    secrets: list[DataResource] = Field(default_factory=list)
    storage: Optional[StorageSpec] = None
    service: Optional[IntentService] = None
    service_account: Optional[ProviderName] = Field(
        default=None, alias="serviceAccount"
    )

    @model_validator(mode="after")
    def validate_references(self) -> "Application":
        for container in self.init:
            if container.health is not None:
                raise ValueError("init containers cannot define health probes")
        containers = [*self.init, *self.containers]
        _reject_duplicates([c.name for c in containers], "container name")
        for resources in (self.configuration, self.secrets):
            _reject_duplicates([r.name for r in resources], "resource name")
        declared = {
            "configuration": {r.name for r in self.configuration},
            "secret": {r.name for r in self.secrets},
            "storage": {self.storage.name} if self.storage else set(),
        }
        for container in containers:
            references = [("configuration", r.name) for r in container.configuration]
            references += [("secret", r.name) for r in container.secrets]
            references += [m.source for m in container.mounts]
            for kind, name in references:
                if name not in declared[kind]:
                    raise ValueError(
                        f"container '{container.name}' references undefined {kind} '{name}'"
                    )
        if self.service:
            if self.service.container is None and len(self.containers) > 1:
                raise ValueError(
                    "service must name the container that receives traffic"
                )
            if self.service.container is not None and self.service.container not in {
                c.name for c in self.containers
            }:
                raise ValueError("service references unknown container")
            target = next(
                c
                for c in self.containers
                if c.name == (self.service.container or self.containers[0].name)
            )
            port = self.service.target_port
            if port is None:
                tcp_ports = [p for p in target.ports if p.protocol == "TCP"]
                if target.ports:
                    if len(tcp_ports) != 1:
                        raise ValueError(
                            "service targetPort is required unless exactly one TCP port is declared"
                        )
                    port = tcp_ports[0].name
                else:
                    port = self.service.port
            if target.ports:
                if not any(
                    p.protocol == "TCP" and (p.name == port or p.port == port)
                    for p in target.ports
                ):
                    raise ValueError(
                        "service targetPort must match a declared TCP port"
                    )
            elif isinstance(port, str):
                raise ValueError(
                    "named service targetPort requires a declared TCP port"
                )
        return self
