# Source guide

One application specification. Deployment-native outputs.

```text
app.yaml -> Parse / Validate -> Application Model
                                  |-- KubernetesRenderer -> Kubernetes manifests YAML
                                  `-- external chart inspection + HelmRenderer -> Helm values YAML
                                                                               + stderr diagnostics
```

| Module | Responsibility |
| --- | --- |
| kubeapp/parser.py | YAML loading and Application validation |
| kubeapp/models/ | Renderer-independent application intent and constraints |
| kubeapp/renderers/kubernetes.py | Kubernetes resource dictionaries |
| kubeapp/renderers/helm.py | Existing Application-to-Helm-values translation |
| kubeapp/chart_inspection.py | External chart validation, metadata and best-effort kind detection |
| kubeapp/value_mapping.py | Declared paths, mapping status and capability notes |
| kubeapp/diagnostics.py | Concise warnings/notes without resolved values |
| kubeapp/cli.py | Options, immutable name override, serialization, streams and atomic file output |
| kubeapp/manifests/ | Kubernetes assembly and compatibility APIs |
| kubeapp/generators.py | Legacy values helper; not the active CLI translator |

## Formats and CLI contract

**One application specification. Deployment-native outputs.**

Kubernetes emits Kubernetes manifests; Helm emits Helm values YAML. The Application
Model is independent of the selected format. Helm generation does not invoke
`helm template` and does not require a Helm executable or Kubernetes cluster.

| Option | Behavior |
| --- | --- |
| `-f / --format` | `kubernetes`, `k8s`, `k` (default: Kubernetes), or `helm`, `h` |
| `-n / --name` | Optional validated Application name override; omission preserves the input name |
| `-c / --chart PATH` | Required for Helm; rejected for Kubernetes; resolved from the current working directory |
| `-o / --output PATH` | Write YAML to this file instead of stdout; parent directories are created |
| `-h / --help` | Standard help, including `kube-app render --help` |

The chart must be a directory containing Chart.yaml. It is inspected, never modified.
Template content supplies best-effort evidence of Deployment, Service, ConfigMap,
Secret and PVC capabilities; filenames do not determine support. Conditions are not
executed, and computed kinds, includes and dependencies are not resolved.

Nested keys in values.yaml and properties in values.schema.json form the union of
the declared values contract. This is path discovery, not JSON Schema validation.
Arrays are compared as whole values; schema references/composition are not resolved.
Declared paths are SUPPORTED; absent paths in an explicit contract are UNSUPPORTED;
insufficient information is UNKNOWN, not proof of missing support.

Unsupported mappings and missing requested capabilities produce WARNING diagnostics.
Unknown mappings may produce NOTE diagnostics. Supported mappings are silent;
equivalent and redundant descendant diagnostics are suppressed. Diagnostics go only
to stderr, while generated YAML goes only to stdout or the requested file. Warnings
and notes are non-fatal (exit 0) and never silently filter or remap generated values.
Arbitrary chart-specific key remapping is not performed: `replicaCount` will not be
translated to `deployment.replicas`. Review the supplied chart's expected keys.

Invalid applications, charts and generation failures exit 1; CLI usage errors exit 2.
Rendering completes before output; file output uses a temporary file and atomic
replacement so failures preserve an existing destination. Successful file output
prints no YAML to stdout. Diagnostics never include resolved Secret values.

The name override creates a newly validated Application without mutating the parsed
model. Derived names, labels/selectors and PVC references follow the override;
explicit container/init, ConfigMap, Secret and serviceAccount names stay unchanged.
Thus a name override alone does not isolate explicitly named shared resources.

Configuration and Secret file paths resolve relative to app.yaml, independently of
working directory. Rendering resolves environment substitutions without changing the
input model or files. Generated values can contain plaintext secrets: keep real
credentials and real-secret outputs out of source control.

Only `-v / --verbose` is deferred for later CLI consideration; it is not implemented.

For Python callers:

```python
from pathlib import Path
from kubeapp.parser import load_application
from kubeapp.renderers import KubernetesRenderer, HelmRenderer

path = Path("examples/advanced/app.yaml")
application = load_application(path)
manifests = KubernetesRenderer().render(application, base_dir=path.parent)
values = HelmRenderer().render(application, base_dir=path.parent)
```

The caller supplies environment substitutions and the application's base directory.
Neither renderer mutates the model. Chart inspection/mapping are separate components;
the CLI coordinates them. See [architecture](../docs/ARCHITECTURE.md) and
[tests](../tests/README.md). The bundled chart is retained for reference/internal tests.

Empty optional resources mappings are omitted for application and init containers.
Explicit empty ports lists remain because they disable chart defaults; populated
resources and intentional enable/create flags are preserved. The reference chart
declares supported optional paths in values.schema.json without activating defaults.
