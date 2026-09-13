from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ApplicationMetadata(BaseModel):
    name: str = Field(min_length=1)


class ServiceSpec(BaseModel):
    port: int = Field(gt=0, le=65535)


class ResourceSpec(BaseModel):
    cpu: Optional[str] = None
    memory: Optional[str] = None


class ResourcesSpec(BaseModel):
    requests: Optional[ResourceSpec] = None
    limits: Optional[ResourceSpec] = None


class ScalingSpec(BaseModel):
    min_replicas: int = Field(default=1, ge=1)
    max_replicas: int = Field(default=1, ge=1)

    def validate_range(self) -> None:
        if self.min_replicas > self.max_replicas:
            raise ValueError(
                "minReplicas cannot be greater than maxReplicas"
            )


class ApplicationSpec(BaseModel):
    image: str = Field(min_length=1)
    service: Optional[ServiceSpec] = None
    resources: Optional[ResourcesSpec] = None
    scaling: Optional[ScalingSpec] = None


class Application(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_version: str = Field(alias="apiVersion")
    kind: str
    metadata: ApplicationMetadata
    spec: ApplicationSpec

    def validate_application(self) -> None:
        if self.api_version != "kubeapp.dev/v1alpha1":
            raise ValueError(
                f"Unsupported apiVersion: {self.api_version}"
            )

        if self.kind != "Application":
            raise ValueError(
                f"Unsupported kind: {self.kind}"
            )

        if self.spec.scaling:
            self.spec.scaling.validate_range()