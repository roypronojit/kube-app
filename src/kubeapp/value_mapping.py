"""Declared value-path comparison; no remapping or JSON Schema validation."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from kubeapp.chart_inspection import CapabilityNote, ChartInspection

ValuePath = tuple[str, ...]


class MappingStatus(str, Enum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ValuesContract:
    declared_paths: frozenset[ValuePath]
    explicit: bool
    unknown_prefixes: frozenset[ValuePath] = frozenset()

    def status(self, path: ValuePath) -> MappingStatus:
        if path in self.declared_paths:
            return MappingStatus.SUPPORTED
        if not self.explicit or any(path[:len(prefix)] == prefix for prefix in self.unknown_prefixes):
            return MappingStatus.UNKNOWN
        return MappingStatus.UNSUPPORTED


@dataclass(frozen=True)
class ValueMappingDiagnostic:
    capability: str
    generated_path: ValuePath
    status: MappingStatus
    reason: str


@dataclass(frozen=True)
class MappingResult:
    # Values can contain resolved secrets; exclude them from diagnostic reprs.
    values: dict[str, Any] = field(repr=False)
    contract: ValuesContract
    diagnostics: tuple[ValueMappingDiagnostic, ...]
    capability_notes: tuple[CapabilityNote, ...]


def _mapping_paths(mapping: dict, prefix: ValuePath = ()) -> set[ValuePath]:
    paths = set()
    for key, value in mapping.items():
        if not isinstance(key, str):
            continue
        path = (*prefix, key)
        paths.add(path)
        if isinstance(value, dict):
            paths.update(_mapping_paths(value, path))
    return paths


def discover_contract(chart: ChartInspection) -> ValuesContract:
    paths = _mapping_paths(chart.values)
    unknown = set()

    def schema_paths(schema, prefix=()):
        if not isinstance(schema, dict):
            return
        # These constructs may declare further paths, but are intentionally not
        # interpreted. Absence of a discovered path here is not proof of absence.
        if any(key in schema for key in ("$ref", "allOf", "anyOf", "oneOf", "if", "then", "else", "patternProperties")):
            unknown.add(prefix)
        properties = schema.get("properties")
        if isinstance(properties, dict):
            for key, child in properties.items():
                path = (*prefix, key)
                paths.add(path)
                schema_paths(child, path)

    schema_paths(chart.values_schema)
    explicit = (chart.path / "values.yaml").is_file() or (
        isinstance(chart.values_schema, dict)
        and isinstance(chart.values_schema.get("properties"), dict)
    )
    return ValuesContract(frozenset(paths), explicit, frozenset(unknown))


def compare_values(values: dict[str, Any], chart: ChartInspection) -> MappingResult:
    contract = discover_contract(chart)
    reasons = {
        MappingStatus.SUPPORTED: "Path is explicitly declared by the chart values contract.",
        MappingStatus.UNSUPPORTED: "Path is not declared by the chart's explicit contract; mapping is unavailable.",
        MappingStatus.UNKNOWN: "Insufficient chart contract information to determine path support.",
    }
    capabilities = {"replicaCount": "replicas", "configuration": "configuration",
                    "secrets": "secrets", "storage": "storage", "service": "service",
                    "serviceAccount": "serviceAccount"}
    diagnostics = tuple(
        ValueMappingDiagnostic(capabilities.get(path[0], "workload"), path,
                               contract.status(path), reasons[contract.status(path)])
        for path in sorted(_mapping_paths(values))
    )
    # Return all generated values intact. Capability notes are carried once,
    # separately from per-path results; no secret values enter diagnostics.
    return MappingResult(values, contract, diagnostics, chart.notes)
