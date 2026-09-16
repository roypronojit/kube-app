"""Shared constrained types and validation helpers."""

import re
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

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


def _present_fields(
    candidates: tuple[tuple[str, object], ...],
) -> list[str]:
    return [name for name, value in candidates if value is not None]


def _reject_duplicates(values: list[str], label: str) -> None:
    duplicates = sorted({value for value in values if values.count(value) > 1})

    if duplicates:
        raise ValueError(f"duplicate {label}: {', '.join(duplicates)}")
