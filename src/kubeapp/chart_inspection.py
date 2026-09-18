"""Best-effort static chart inspection, without rendering or value mapping.

Literal kind declarations (including conditional branches and quoted literal
template expressions) are evidence of possible support, not rendered resources.
Dynamic includes, computed kinds, dependencies, and enabled conditions are not
evaluated. Template filenames never determine capabilities.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from kubeapp.models import Application


@dataclass(frozen=True)
class CapabilityNote:
    capability: str
    expected_kind: str
    message: str
    code: str = "undetected-chart-capability"


@dataclass(frozen=True)
class ChartInspection:
    path: Path
    metadata: dict[str, Any]
    values: dict[str, Any]
    values_schema: dict[str, Any] | None
    detected_kinds: frozenset[str]
    notes: tuple[CapabilityNote, ...]


def validate_chart_path(path: str | Path) -> Path:
    """Resolve chart paths against the caller's current working directory."""
    chart = Path(path).resolve()
    if not chart.exists():
        raise ValueError(f"Chart path does not exist: {chart}")
    if not chart.is_dir():
        raise ValueError(f"Chart path is not a directory: {chart}")
    if not (chart / "Chart.yaml").is_file():
        raise ValueError(f"Chart.yaml is missing or is not a file: {chart}")
    return chart


def _read_mapping(path: Path, *, json_format: bool = False) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
        value = json.loads(text) if json_format else yaml.safe_load(text)
    except (ValueError, yaml.YAMLError, UnicodeError) as exc:
        raise ValueError(f"Cannot parse chart configuration: {path}") from exc
    if value is None and not json_format:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"Chart configuration must be an object: {path}")
    return value


def _literal_kinds(text: str) -> set[str]:
    text = re.sub(r"{{-?\s*/\*.*?\*/\s*-?}}", "", text, flags=re.DOTALL)

    def expression(match):
        body = match.group(1).strip().strip("-").strip()
        literal = re.fullmatch(r'''["'`]([A-Za-z][A-Za-z0-9]*)["'`]''', body)
        if literal:
            return literal.group(1)
        if re.match(r"(?:if|else|end|with|range)\b", body):
            return " "
        return "__dynamic__"

    text = re.sub(r"{{(.*?)}}", expression, text, flags=re.DOTALL)
    kinds = set()
    # Only root-level declarations are considered, avoiding embedded YAML in data.
    for line in text.splitlines():
        if line.startswith("kind:"):
            value = line[5:].split("#", 1)[0].strip()
            for token in value.split():
                token = token.strip("\"'")
                if token in {"Deployment", "Service", "ConfigMap", "Secret", "PersistentVolumeClaim"}:
                    kinds.add(token)
    return kinds


def capability_notes(application: Application, kinds: frozenset[str]) -> tuple[CapabilityNote, ...]:
    requirements = (
        ("workload", "Deployment", True),
        ("service", "Service", application.service is not None),
        ("configuration", "ConfigMap", bool(application.configuration)),
        ("secrets", "Secret", bool(application.secrets)),
        ("storage", "PersistentVolumeClaim", application.storage is not None),
    )
    return tuple(
        CapabilityNote(capability, kind,
                       f'Application capability "{capability}" could not be mapped to the supplied '
                       f'Helm chart because no {kind} template was detected.')
        for capability, kind, requested in requirements if requested and kind not in kinds
    )


def inspect_chart(path: str | Path, application: Application) -> ChartInspection:
    chart = validate_chart_path(path)
    metadata = _read_mapping(chart / "Chart.yaml")
    values = _read_mapping(chart / "values.yaml") if (chart / "values.yaml").exists() else {}
    schema = (_read_mapping(chart / "values.schema.json", json_format=True)
              if (chart / "values.schema.json").exists() else None)
    kinds: set[str] = set()
    templates = chart / "templates"
    if templates.exists():
        for template in sorted(templates.rglob("*")):
            if template.is_file():
                kinds.update(_literal_kinds(template.read_text(encoding="utf-8")))
    detected = frozenset(kinds)
    return ChartInspection(chart, metadata, values, schema, detected,
                           capability_notes(application, detected))
