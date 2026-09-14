import re
from typing import Annotated, Any, Literal, Optional

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

DNS_LABEL_PATTERN = r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$"
DNS_SUBDOMAIN_PATTERN = r"^[a-z0-9]([-a-z0-9.]*[a-z0-9])?$"
ENVIRONMENT_NAME_PATTERN = r"^[A-Za-z_][A-Za-z0-9_]*$"
PROVIDER_KEY_PATTERN = r"^[-._a-zA-Z0-9]+$"
IMAGE_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:/@-]*$"

AccessMode = Literal[
    "ReadWriteOnce",
    "ReadOnlyMany",
    "ReadWriteMany",
    "ReadWriteOncePod",
]

ServiceType = Literal[
    "ClusterIP",
    "NodePort",
    "LoadBalancer",
]

_STORAGE_SIZE_PATTERN = re.compile(
    r"(?P<amount>[0-9]+(\.[0-9]+)?)(Ki|Mi|Gi|Ti|Pi|Ei|k|M|G|T|P|E)?"
)


def _as_environment_value(value: Any) -> Any:
    """Accept the scalars YAML produces for a configuration value."""

    if isinstance(value, bool):
        return "true" if value else "false"

    if isinstance(value, (int, float)):
        return str(value)

    return value


#: Name of an environment variable the application reads.
EnvironmentName = Annotated[
    str,
    Field(min_length=1, pattern=ENVIRONMENT_NAME_PATTERN),
]

#: Literal configuration value.
EnvironmentValue = Annotated[
    str,
    BeforeValidator(_as_environment_value),
]

#: Name of something the platform manages outside the application.
ProviderName = Annotated[
    str,
    Field(min_length=1, max_length=253, pattern=DNS_SUBDOMAIN_PATTERN),
]

#: Key of a single entry inside a provider.
ProviderKey = Annotated[
    str,
    Field(min_length=1, max_length=253, pattern=PROVIDER_KEY_PATTERN),
]

#: Container image reference.
ImageReference = Annotated[
    str,
    Field(min_length=1, max_length=512, pattern=IMAGE_PATTERN),
]

#: Name chosen by the application for one of its own parts.
LocalName = Annotated[
    str,
    Field(min_length=1, max_length=63, pattern=DNS_LABEL_PATTERN),
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ApplicationMetadata(StrictModel):
    name: str = Field(
        min_length=1,
        max_length=63,
        pattern=DNS_LABEL_PATTERN,
    )


class SecretValueSource(StrictModel):
    """One entry of a sensitive provider the platform manages."""

    name: ProviderName
    key: ProviderKey


class ConfigValueSource(StrictModel):
    """One entry of a configuration provider the platform manages."""

    name: ProviderName
    key: ProviderKey


class SecretFileSource(StrictModel):
    """A sensitive provider consumed as files."""

    name: ProviderName


class ConfigFileSource(StrictModel):
    """A configuration provider consumed as files."""

    name: ProviderName


class EnvironmentVariable(StrictModel):
    """One environment variable and where its value comes from."""

    name: EnvironmentName
    value: Optional[EnvironmentValue] = None
    secret: Optional[SecretValueSource] = None
    config: Optional[ConfigValueSource] = None

    @model_validator(mode="after")
    def validate_single_source(self) -> "EnvironmentVariable":
        sources = _present_fields(
            (
                ("value", self.value),
                ("secret", self.secret),
                ("config", self.config),
            )
        )

        if not sources:
            raise ValueError(
                f"environment variable '{self.name}' must define one of "
                "value, secret or config"
            )

        if len(sources) > 1:
            raise ValueError(
                f"environment variable '{self.name}' must define only one of "
                f"value, secret or config, got {', '.join(sources)}"
            )

        return self


class MountSpec(StrictModel):
    """Something the application expects to find on its filesystem."""

    name: LocalName
    path: str = Field(min_length=1)
    config: Optional[ConfigFileSource] = None
    secret: Optional[SecretFileSource] = None
    storage: Optional[LocalName] = None

    @property
    def source(self) -> tuple[str, str]:
        """Identity of what is mounted, independent of the path."""

        if self.config is not None:
            return ("config", self.config.name)

        if self.secret is not None:
            return ("secret", self.secret.name)

        if self.storage is not None:
            return ("storage", self.storage)

        raise ValueError(f"mount '{self.name}' has no source")

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError(f"path must start with '/', got '{value}'")

        return value

    @model_validator(mode="after")
    def validate_single_source(self) -> "MountSpec":
        sources = _present_fields(
            (
                ("config", self.config),
                ("secret", self.secret),
                ("storage", self.storage),
            )
        )

        if not sources:
            raise ValueError(
                f"mount '{self.name}' must define one of config, secret or storage"
            )

        if len(sources) > 1:
            raise ValueError(
                f"mount '{self.name}' must define only one of "
                f"config, secret or storage, got {', '.join(sources)}"
            )

        return self


class ResourceSpec(StrictModel):
    cpu: Optional[str] = None
    memory: Optional[str] = None


class ResourcesSpec(StrictModel):
    requests: Optional[ResourceSpec] = None
    limits: Optional[ResourceSpec] = None


class ContainerSpec(StrictModel):
    """One part of the application that runs as its own process."""

    name: LocalName
    image: ImageReference
    environment: list[EnvironmentVariable] = Field(default_factory=list)
    mounts: list[MountSpec] = Field(default_factory=list)
    resources: Optional[ResourcesSpec] = None

    @model_validator(mode="after")
    def validate_unique_names(self) -> "ContainerSpec":
        _reject_duplicates(
            [variable.name for variable in self.environment],
            f"environment variable name in container '{self.name}'",
        )
        _reject_duplicates(
            [mount.name for mount in self.mounts],
            f"mount name in container '{self.name}'",
        )
        _reject_duplicates(
            [mount.path for mount in self.mounts],
            f"mount path in container '{self.name}'",
        )

        return self


class StorageSpec(StrictModel):
    """Persistent application data the platform provisions."""

    name: LocalName
    size: str = Field(min_length=1)
    storage_class: Optional[ProviderName] = Field(
        default=None,
        alias="storageClass",
    )
    access_modes: list[AccessMode] = Field(
        default_factory=lambda: ["ReadWriteOnce"],
        alias="accessModes",
        min_length=1,
    )

    @field_validator("size")
    @classmethod
    def validate_size(cls, value: str) -> str:
        match = _STORAGE_SIZE_PATTERN.fullmatch(value)

        if match is None:
            raise ValueError(
                f"size must be an amount of storage such as '10Gi', got '{value}'"
            )

        if float(match.group("amount")) <= 0:
            raise ValueError(f"size must be greater than zero, got '{value}'")

        return value


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


def _present_fields(
    candidates: tuple[tuple[str, object], ...],
) -> list[str]:
    return [name for name, value in candidates if value is not None]


def _reject_duplicates(values: list[str], label: str) -> None:
    duplicates = sorted({value for value in values if values.count(value) > 1})

    if duplicates:
        raise ValueError(f"duplicate {label}: {', '.join(duplicates)}")


class DataResource(StrictModel):
    name: LocalName
    data: Optional[dict[ProviderKey, EnvironmentValue]] = None
    file: Optional[str] = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def single_source(self) -> "DataResource":
        if (self.data is None) == (self.file is None):
            raise ValueError("define exactly one of data or file")
        return self


class ResourceConsumption(StrictModel):
    name: LocalName
    as_: Literal["environment"] = Field(alias="as")


class IntentMount(StrictModel):
    configuration: Optional[LocalName] = None
    secret: Optional[LocalName] = None
    storage: Optional[LocalName] = None
    path: str = Field(pattern=r"^/")

    @model_validator(mode="after")
    def single_source(self) -> "IntentMount":
        if (
            sum(v is not None for v in (self.configuration, self.secret, self.storage))
            != 1
        ):
            raise ValueError(
                "mount must define exactly one of configuration, secret or storage"
            )
        return self

    @property
    def source(self) -> tuple[str, str]:
        return next(
            (k, getattr(self, k))
            for k in ("configuration", "secret", "storage")
            if getattr(self, k) is not None
        )


class ResourceRange(StrictModel):
    min: Optional[EnvironmentValue] = None
    max: Optional[EnvironmentValue] = None

    @model_validator(mode="after")
    def valid_range(self) -> "ResourceRange":
        amounts = []
        for value in (self.min, self.max):
            if value is None:
                amounts.append(None)
                continue
            match = re.fullmatch(
                r"([0-9]+(?:\.[0-9]+)?)(m|Ki|Mi|Gi|Ti|Pi|Ei|k|M|G|T|P|E)?", value
            )
            if match is None:
                raise ValueError("invalid resource quantity")
            suffix = match[2] or ""
            factor = {
                "": 1,
                "m": 0.001,
                **{
                    s: 1024**i
                    for i, s in enumerate(("Ki", "Mi", "Gi", "Ti", "Pi", "Ei"), 1)
                },
                **{s: 1000**i for i, s in enumerate(("k", "M", "G", "T", "P", "E"), 1)},
            }[suffix]
            amounts.append(float(match[1]) * factor)
        if all(v is not None for v in amounts) and amounts[0] > amounts[1]:
            raise ValueError("resource min cannot exceed max")
        return self


class IntentResources(StrictModel):
    cpu: Optional[ResourceRange] = None
    memory: Optional[ResourceRange] = None


class IntentContainer(StrictModel):
    name: LocalName
    image: ImageReference
    environment: dict[EnvironmentName, EnvironmentValue] = Field(default_factory=dict)
    configuration: list[ResourceConsumption] = Field(default_factory=list)
    secrets: list[ResourceConsumption] = Field(default_factory=list)
    mounts: list[IntentMount] = Field(default_factory=list)
    resources: Optional[IntentResources] = None

    @model_validator(mode="after")
    def unique_consumption(self) -> "IntentContainer":
        _reject_duplicates([m.path for m in self.mounts], "mount path")
        for references in (self.configuration, self.secrets):
            _reject_duplicates([r.name for r in references], "resource reference")
        return self


class Application(StrictModel):
    """Public application intent, independent of any renderer."""

    name: LocalName
    replicas: int = Field(default=1, ge=0, strict=True)
    containers: list[IntentContainer] = Field(min_length=1)
    init: list[IntentContainer] = Field(default_factory=list)
    configuration: list[DataResource] = Field(default_factory=list)
    secrets: list[DataResource] = Field(default_factory=list)
    storage: Optional[StorageSpec] = None
    service: Optional[ServiceSpec] = None
    service_account: Optional[ProviderName] = Field(
        default=None, alias="serviceAccount"
    )

    @model_validator(mode="after")
    def validate_references(self) -> "Application":
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
        return self
