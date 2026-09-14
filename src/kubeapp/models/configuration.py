"""Configuration, secrets, mounts, and persistent storage models."""

from typing import Literal, Optional

from pydantic import Field, field_validator, model_validator

from .common import (
    _STORAGE_SIZE_PATTERN,
    AccessMode,
    EnvironmentName,
    EnvironmentValue,
    LocalName,
    ProviderKey,
    ProviderName,
    StrictModel,
    _present_fields,
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
