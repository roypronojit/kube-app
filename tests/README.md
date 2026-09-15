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

No running Kubernetes cluster or Helm installation is needed for this suite.

| Module | Coverage |
| --- | --- |
| `cli_tests/test_commands.py` | Validation/render commands, exit codes, output files, and failed-render diagnostics |
| `cli_tests/test_parser.py` | YAML and filesystem input errors through the parser API |
| `manifest_tests/test_intent.py` | Flat schema, defaults, resource wiring, file inputs, substitution, and example snapshots |
| `model_tests/test_application.py` | Application/container composition, services, identities, and init-container validation |
| `model_tests/test_configuration.py` | Environment values and configuration/secret references |
| `model_tests/test_storage.py` | Mount and persistent-storage validation |
| `manifest_tests/test_deployment.py` | Deployment/container rendering, service wiring, init containers, identities, and label consistency |
| `manifest_tests/test_resources.py` | Environment, substitution, mount permissions, resource ranges, and persistent-volume rendering |
| `manifest_tests/test_examples.py` | Advanced example resource wiring and ordering |
| `manifest_tests/test_runtime.py` | Runtime validation, health probes, ports, and deterministic rendering |
| `manifest_tests/test_generators.py` | Compatibility tests for the deferred Helm values generator |
| `manifest_tests/test_renderers.py` | Kubernetes adapter parity, model immutability, base directory handling, and legacy compatibility |

The CLI/input, model, and manifest test packages keep reusable fixtures and builders in
their respective `helpers.py` modules. Parser tests live with CLI/input tests; intent and runtime tests exercise validation
through rendering, and the deferred Helm generator is kept with manifest output tests.
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
this is not part of the Python test suite or the current CLI render path.


Version 0.1.1 adds container ports, image pull policy, HTTP health probes,
and command/args. See [runtime configuration](../docs/RENDERING.md#runtime-configuration-v011).

`manifest_tests/test_runtime.py` covers runtime field validation, service/probe port wiring,
process overrides, omission of implicit security contexts, and deterministic rendering.
