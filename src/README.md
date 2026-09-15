# Source code

The `kubeapp/` package implements the application model, validation, Kubernetes renderer, and CLI. From the repository root,
install it with Python 3.11 or later:

```sh
python -m pip install -e .
python -m kubeapp validate examples/basic/app.yaml
python -m kubeapp render examples/basic/app.yaml
```

Installation also exposes the equivalent `kube-app` command.

| Module | Responsibility |
| --- | --- |
| `kubeapp/__init__.py` | Package version |
| `kubeapp/__main__.py` | Entry point for `python -m kubeapp` |
| `kubeapp/cli.py` | Argument parsing, validate/render commands, output and error handling |
| `kubeapp/parser.py` | YAML loading and application validation; `ApplicationParseError` |
| `kubeapp/renderers/` | Generic `Renderer[Output]` protocol and `KubernetesRenderer` adapter used by the CLI |
| `kubeapp/models/` | Application schema and compatibility exports; domains split across `application`, `container`, `configuration`, and `common` |
| `kubeapp/manifests/` | Rendering entry point and compatibility exports; `deployment`, `containers`, `resources`, and `common` handle resource assembly |
| `kubeapp/generators.py` | Compatibility code for the deferred Helm values renderer |

Model modules depend on shared types and domain models; application-level validation
combines them. The renderer entry point preserves resource ordering, while deployment
and container assembly are separate from ConfigMap, Secret, PVC, and Service rendering.
Existing imports from `kubeapp.models` and `kubeapp.manifests` remain supported.

The current rendering path is:

app.yaml → CLI → Parser → Application Model → Kubernetes Renderer → Kubernetes manifests


Helm integration is deferred. The existing Helm values generator is retained for compatibility and is not used by the current render command.

For Python callers, preserve the application's directory when rendering:

```python
from pathlib import Path

from kubeapp.parser import load_application
from kubeapp.manifests import application_to_kubernetes_manifests

path = Path("examples/basic/app.yaml")
application = load_application(path)
manifests = application_to_kubernetes_manifests(application, base_dir=path.parent)
```

`manifests` is a list of resource dictionaries. The base directory matters for
file-based inputs such as those in `examples/advanced/app.yaml`.

Keep schema validation in the model, file loading in the parser, and resource
translation in the renderer. See [architecture](../docs/ARCHITECTURE.md),
[rendering semantics](../docs/RENDERING.md), and the [test guide](../tests/README.md).
Generated `*.egg-info/` and `__pycache__/` directories are development artifacts.


Version 0.1.1 adds container ports, image pull policy, HTTP health probes,
and command/args. See [runtime configuration](../docs/RENDERING.md#runtime-configuration-v011).
