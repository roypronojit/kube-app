# Tests

Run from the repository root using the existing WSL environment:

```sh
.venv/bin/python -m unittest discover -s tests -v
```

No Kubernetes cluster is required. Public CLI tests use temporary charts/applications
and verify generation without Helm on PATH. Internal reference-chart template tests
in manifest_tests/test_chart.py require Helm and skip when it is absent. They verify
that the reference chart consumes generated values; they do not define public CLI
output equivalence. Kubernetes output is manifests; Helm output is values YAML.

| Tests | Coverage |
| --- | --- |
| model_tests/ | Schema, defaults, references, storage and runtime validation |
| cli_tests/test_parser.py | File/YAML errors and sanitized validation |
| cli_tests/test_commands.py | Options, aliases, names, validation and output |
| cli_tests/test_equivalence.py | Each public output matches its backend, app-relative files, substitutions, empty PATH and failure preservation |
| cli_tests/test_chart_inspection.py | Temporary chart validation and best-effort capabilities |
| cli_tests/test_value_mapping.py | Nested contract union, supported/unsupported/unknown paths, unchanged values and safe diagnostics |
| cli_tests/test_diagnostics.py | stderr isolation, deduplication, severity, help and atomic output failures |
| manifest_tests/test_helm_renderer.py | Values translation, order, limits and immutability |
| manifest_tests/test_helm_files.py | File inputs/substitution and renderer error parity |
| manifest_tests/test_chart.py | Optional bundled reference-chart consumption regression tests |
| manifest_tests/test_intent.py | Kubernetes example snapshots and resource wiring |
| Other manifest_tests/ | Kubernetes behavior, runtime, ordering and legacy API compatibility |

Example snapshots use examples/{basic,medium,advanced}/kubernetes-manifests.yaml and
helm-values.yaml, with demonstration credentials only. YAML is compared structurally;
ordered lists remain significant. Internal reference-chart comparisons use the
established semantic normalization, never to equate public Helm values with manifests.
Run `helm lint charts/kube-app` separately when validating the reference chart.
The complete suite must retain meaningful model, renderer, security, file input,
immutability and failure-preservation coverage. No real credentials belong in tests.
