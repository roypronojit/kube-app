"""Container resources, ports, health checks, and runtime validation."""

import re
from typing import Annotated, Literal, Optional

from pydantic import AliasChoices, Field, model_validator

from .common import (
    EnvironmentName,
    EnvironmentValue,
    ImageReference,
    LocalName,
    StrictModel,
    _reject_duplicates,
)
from .configuration import (
    EnvironmentVariable,
    IntentMount,
    MountSpec,
    ResourceConsumption,
)


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


PortNumber = Annotated[int, Field(strict=True, ge=1, le=65535)]


PortName = Annotated[
    str, Field(min_length=1, max_length=15, pattern=r"^[a-z]([-a-z0-9]*[a-z0-9])?$")
]


class ContainerPort(StrictModel):
    name: PortName
    port: PortNumber
    protocol: Literal["TCP", "UDP", "SCTP"] = "TCP"


class HealthProbe(StrictModel):
    """An HTTP endpoint checked by Kubernetes."""

    path: str = Field(pattern=r"^/")
    port: PortNumber | PortName
    initial_delay_seconds: int = Field(
        default=0, alias="initialDelaySeconds", ge=0, strict=True
    )
    period_seconds: int = Field(
        default=10,
        alias="periodSeconds",
        validation_alias=AliasChoices("frequencySeconds", "periodSeconds"),
        ge=1,
        strict=True,
    )
    timeout_seconds: int = Field(default=1, alias="timeoutSeconds", ge=1, strict=True)
    failure_threshold: int = Field(
        default=3, alias="failureThreshold", ge=1, strict=True
    )
    success_threshold: int = Field(
        default=1, alias="successThreshold", ge=1, strict=True
    )


class Health(StrictModel):
    readiness: Optional[HealthProbe] = Field(
        default=None, validation_alias=AliasChoices("ready", "readiness")
    )
    liveness: Optional[HealthProbe] = Field(
        default=None, validation_alias=AliasChoices("live", "liveness")
    )
    startup: Optional[HealthProbe] = None

    @model_validator(mode="after")
    def validate_probes(self) -> "Health":
        if not any((self.readiness, self.liveness, self.startup)):
            raise ValueError("health must define at least one probe")
        for probe in (self.liveness, self.startup):
            if probe is not None and probe.success_threshold != 1:
                raise ValueError("liveness and startup successThreshold must be 1")
        return self


class IntentContainer(StrictModel):
    name: LocalName
    image: ImageReference
    environment: dict[EnvironmentName, EnvironmentValue] = Field(default_factory=dict)
    configuration: list[ResourceConsumption] = Field(default_factory=list)
    secrets: list[ResourceConsumption] = Field(default_factory=list)
    mounts: list[IntentMount] = Field(default_factory=list)
    resources: Optional[IntentResources] = None
    ports: list[ContainerPort] = Field(default_factory=list)
    health: Optional[Health] = Field(
        default=None,
        validation_alias=AliasChoices("healthChecks", "healthCheck", "health"),
    )
    command: Optional[list[str]] = Field(default=None, min_length=1)
    args: Optional[list[str]] = Field(default=None, min_length=1)
    image_pull_policy: Literal["Always", "IfNotPresent", "Never"] = Field(
        default="IfNotPresent", alias="imagePullPolicy"
    )

    @model_validator(mode="after")
    def validate_runtime(self) -> "IntentContainer":
        _reject_duplicates([p.name for p in self.ports], "container port name")
        _reject_duplicates(
            [f"{p.port}/{p.protocol}" for p in self.ports], "container port"
        )
        if self.command is not None and not self.command[0].strip():
            raise ValueError("command executable must not be empty")
        if self.health:
            tcp_names = {p.name for p in self.ports if p.protocol == "TCP"}
            for probe in (
                self.health.readiness,
                self.health.liveness,
                self.health.startup,
            ):
                if (
                    probe
                    and isinstance(probe.port, str)
                    and probe.port not in tcp_names
                ):
                    raise ValueError("health probe references unknown TCP port")
        return self

    @model_validator(mode="after")
    def unique_consumption(self) -> "IntentContainer":
        _reject_duplicates([m.path for m in self.mounts], "mount path")
        for references in (self.configuration, self.secrets):
            _reject_duplicates([r.name for r in references], "resource reference")
        return self
