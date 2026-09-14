# Rendering applications

The public schema is described in [ARCHITECTURE.md](ARCHITECTURE.md). The
`basic`, `medium`, and `advanced` examples use the same schema. `render`
produces Kubernetes YAML directly; Helm integration remains deferred.

```sh
kube-app validate examples/medium/app.yaml
kube-app render examples/medium/app.yaml -o examples/medium/rendered.yaml
```

Without `-o` / `--output`, manifests go to standard output. Parent output
directories are created as needed. Validation checks the model and resource
references; resource files and environment substitutions are resolved only
during rendering. Render errors return exit code 1 before writing output.

`replicas` defaults to 1 and accepts 0 to stop the workload. Resource `min`
values become requests; `max` values become limits. Service type defaults to
ClusterIP. A service with multiple application containers requires an explicit
`container` target. Init containers cannot be service targets.

Top-level configuration and secrets create ConfigMaps and Opaque Secrets.
Each resource requires exactly one of `data` or `file`. Container references
with `as: environment` become `envFrom`; explicit `environment` values become
`env` and take precedence. Mounts expose resource keys as files beneath the
specified path. Configuration and secret mounts are read-only. Storage creates
a PVC and relies on the selected storage class for provisioning. Resources may
be declared without being consumed. `serviceAccount` references an existing
account; it does not create an account or RBAC.

File paths resolve relative to the application YAML file. Files use UTF-8,
simple `KEY=value` entries, one per line, as shown in the example `.properties`
and `.env` files. Blank lines and lines starting with `#` or `!` are ignored.
Whitespace around keys and values is trimmed; empty values are supported.
Duplicate keys and malformed entries are rejected. Values may contain `=`.
Quotes are literal; shell syntax, Java properties escapes, and multiline
continuations are not interpreted. Each entry becomes one resource key, so
the same resource can be consumed as environment variables or mounted files.

`${VARIABLE}` in inline or file-based resource values is replaced from the
rendering process's environment. Missing variables fail rendering. Substitution
does not execute shell commands and is performed once. Use environment-safe
keys when consuming a resource as environment variables.

The advanced example includes demonstration database values. To reproduce its
checked-in output with a demonstration API key:

```sh
CATALOG_API_KEY=example-api-key kube-app render examples/advanced/app.yaml -o examples/advanced/rendered.yaml
```

PowerShell equivalent:

```powershell
$env:CATALOG_API_KEY = 'example-api-key'
kube-app render examples/advanced/app.yaml -o examples/advanced/rendered.yaml
```

Rendered Secret manifests contain sensitive values. Do not commit real secrets
or real-secret outputs. The provided examples and outputs contain placeholders.

For direct Python use, call `load_application(path)` and then
`application_to_kubernetes_manifests(application, base_dir=path.parent)`.
Rendering preserves declaration order and is deterministic for the same
application, file contents, and environment.

The previous model is retained as `LegacyApplication` for existing Python
callers and regression tests. The CLI accepts the new flat schema only.
`application_to_helm_values` remains a legacy API, not the public render path.

Run tests with Python 3.11 or later:

```sh
python -m pip install -e .
python -m unittest discover -s tests -v
```
