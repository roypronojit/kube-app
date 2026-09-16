# Source code

The `kubeapp/` package implements the application model, validation, Kubernetes and Helm renderers, and CLI. From the repository root,
install it with Python 3.11 or later:

```sh
python -m pip install -e .
python -m kubeapp validate examples/basic/app.yaml
python -m kubeapp render examples/basic/app.yaml
kube-app render examples/basic/app.yaml -r kubernetes
kube-app render examples/basic/app.yaml --renderer helm
```

Installation also exposes the equivalent `kube-app` command.

| Module | Responsibility |
| --- | --- |
| `kubeapp/__init__.py` | Package version |
| `kubeapp/__main__.py` | Entry point for `python -m kubeapp` |
| `kubeapp/cli.py` | Argument parsing, renderer selection, helm template execution, output and error handling |
| `kubeapp/parser.py` | YAML loading and application validation; `ApplicationParseError` |
| `kubeapp/renderers/` | Generic `Renderer[Output]` protocol, `KubernetesRenderer` resource adapter, and `HelmRenderer` values translation |
| `kubeapp/models/` | Application schema and compatibility exports; domains split across `application`, `container`, `configuration`, and `common` |
| `kubeapp/manifests/` | Rendering entry point and compatibility exports; `deployment`, `containers`, `resources`, and `common` handle resource assembly |
| `kubeapp/generators.py` | Legacy-schema Helm values compatibility API; separate from HelmRenderer |

Model modules depend on shared types and domain models; application-level validation
combines them. The renderer entry point preserves resource ordering, while deployment
and container assembly are separate from ConfigMap, Secret, PVC, and Service rendering.
Existing imports from `kubeapp.models` and `kubeapp.manifests` remain supported.

The implemented rendering paths are:

```text
app.yaml -> CLI -> Parser -> validated Application
  -> KubernetesRenderer -> resource dictionaries -> YAML
  -> HelmRenderer -> values -> helm template charts/kube-app -> YAML
```

The Application model imports no renderer code. Kubernetes is the default.
`--renderer` / `-r` accepts `kubernetes`, `k8s`, `k` or `helm`, `h`, normalizing
aliases to canonical names. Both paths output final Kubernetes YAML to stdout
or `-o` / `--output`. Only the Helm path needs Helm installed on `PATH`.
Helm renders the application locally; it does not deploy kube-app or install a release.
The compatibility `application_to_helm_values` function is separate from this CLI path.

For Python callers, preserve the application's directory when rendering:

```python
from pathlib import Path

from kubeapp.parser import load_application
from kubeapp.renderers import KubernetesRenderer, HelmRenderer

path = Path("examples/basic/app.yaml")
application = load_application(path)
manifests = KubernetesRenderer().render(application, base_dir=path.parent)
values = HelmRenderer().render(application, base_dir=path.parent)
```

`manifests` is a list of resource dictionaries. `values` is a Helm values dictionary;
Python callers own Helm execution, while the CLI handles it for end users. The base directory matters for
file-based inputs such as those in `examples/advanced/app.yaml`.

Keep schema validation in the model, file loading in the parser, and resource
translation in the renderer. See [architecture](../docs/ARCHITECTURE.md),
[rendering semantics](../docs/RENDERING.md), and the [test guide](../tests/README.md).
Generated `*.egg-info/` and `__pycache__/` directories are development artifacts.


Version 0.1.1 adds container ports, image pull policy, HTTP health probes,
and command/args. See [runtime configuration](../docs/RENDERING.md#runtime-configuration-v011).
