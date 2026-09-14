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
| `test_cli.py` | CLI rendering, stdout/output-file behavior and missing input |
| `test_intent.py` | Flat schema, defaults, resource wiring, file inputs, substitution and failed renders |
| `test_models.py` | Application schema validation, defaults, constraints, and compatibility regressions |
| `test_manifests.py` | Example output comparisons and resource rendering, including legacy cases |
| `test_generators.py` | Compatibility tests for the deferred Helm values generator |

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
