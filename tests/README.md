# Tests

The test suite uses Python's standard-library unittest framework. From the repository
root with Python 3.11 or later:

```sh
python -m pip install -e .
python -m unittest discover -s tests -v
```

Run one module with a discovery pattern:

```sh
python -m unittest discover -s tests -p "test_intent.py" -v
```

No running Kubernetes cluster is needed. Chart template and Helm CLI integration
tests require Helm on PATH and are skipped otherwise. Install the package as above
so end-to-end tests can invoke the public kube-app command.

| Module | Coverage |
| --- | --- |
| `manifest_tests/test_helm_files.py` | Relative configuration/Secret files, substitution, matching file errors, and model immutability |
| `manifest_tests/test_chart.py` | Basic/Medium/Advanced semantic equivalence, resources, ordered application/init containers, probes, ports, and service account references (requires Helm) |
| `manifest_tests/test_helm_renderer.py` | Basic/Medium/Advanced values, file and inline resources, storage, mounts, probes, ordering, immutability, and capability limits |
| `cli_tests/test_commands.py` | Validation/render commands, exit codes, output files, and failed-render diagnostics |
| `cli_tests/test_equivalence.py` | Public CLI equivalence for all examples, stdout/files, defaults/aliases, external working directories, and failure output preservation (requires Helm) |
| `semantic_helpers.py` | Shared renderer/CLI normalization and complete resource comparison |
| `cli_tests/test_parser.py` | YAML and filesystem input errors through the parser API |
| `manifest_tests/test_intent.py` | Flat schema, defaults, resource wiring, file inputs, substitution, and example snapshots |
| `model_tests/test_application.py` | Application/container composition, services, identities, and init-container validation |
| `model_tests/test_configuration.py` | Environment values and configuration/secret references |
| `model_tests/test_storage.py` | Mount and persistent-storage validation |
| `manifest_tests/test_deployment.py` | Deployment/container rendering, service wiring, init containers, identities, and label consistency |
| `manifest_tests/test_resources.py` | Environment, substitution, mount permissions, resource ranges, and persistent-volume rendering |
| `manifest_tests/test_examples.py` | Advanced example resource wiring and ordering |
| `manifest_tests/test_runtime.py` | Runtime validation, health probes, ports, and deterministic rendering |
| `manifest_tests/test_generators.py` | Compatibility tests for the legacy-schema Helm values helper |
| `manifest_tests/test_renderers.py` | Kubernetes adapter parity, model immutability, base directory handling, and legacy compatibility |

The CLI/input, model, and manifest test packages keep reusable fixtures and builders in
their respective `helpers.py` modules. Parser tests live with CLI/input tests; intent and runtime tests exercise validation
through rendering, and the legacy-schema Helm helper is kept with manifest output tests.
Group tests by responsibility rather than
line count; keep related cases together and avoid duplicating example snapshots.
Package `__init__.py` files allow the standard discovery command to find all tests.
To run just model tests: `python -m unittest discover -s tests/model_tests -t tests -v`.

Example fixtures live in `examples/{basic,medium,advanced}/app.yaml`; expected
outputs live beside them as `rendered.yaml`. Tests compare parsed YAML rather
than formatting. The advanced fixture resolves files relative to
`examples/advanced/` and patches `CATALOG_API_KEY` with a demonstration value.
Other file-input tests use temporary directories.

When an intentional rendering or example change affects expected resources,
regenerate the affected output using the [example guide](../examples/README.md),
review the change, and rerun the suite. Keep real credentials out of fixtures.

The Helm chart can be checked separately with `helm lint charts/kube-app`;
lint is separate from the Python suite. Helm-backed CLI tests run helm template
against this same chart.


Version 0.1.1 adds container ports, image pull policy, HTTP health probes,
and command/args. See [runtime configuration](../docs/RENDERING.md#runtime-configuration-v011).

`manifest_tests/test_runtime.py` covers runtime field validation, service/probe port wiring,
process overrides, omission of implicit security contexts, and deterministic rendering.
