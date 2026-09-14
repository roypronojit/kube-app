# Examples

Basic, medium, and advanced demonstrate progressively richer applications using
the same flat schema. Each directory keeps its input (`app.yaml`) beside its
checked-in Kubernetes output (`rendered.yaml`).

| Example | Input | Generated output | Features |
| --- | --- | --- | --- |
| Basic | [app.yaml](basic/app.yaml) | [rendered.yaml](basic/rendered.yaml) | One container, ports, image pull policy, resources, ClusterIP service |
| Medium | [app.yaml](medium/app.yaml) | [rendered.yaml](medium/rendered.yaml) | HTTP health probes, inline configuration and secrets, mounts, PVC, LoadBalancer service |
| Advanced | [app.yaml](advanced/app.yaml) | [rendered.yaml](advanced/rendered.yaml) | Command/args, file inputs, multiple containers, init container, existing service account |

Run these commands from the repository root with Python 3.11 or later:

```sh
python -m pip install -e .
kube-app validate examples/basic/app.yaml
kube-app render examples/basic/app.yaml -o examples/basic/rendered.yaml
kube-app validate examples/medium/app.yaml
kube-app render examples/medium/app.yaml -o examples/medium/rendered.yaml
kube-app validate examples/advanced/app.yaml
CATALOG_API_KEY=example-api-key kube-app render examples/advanced/app.yaml -o examples/advanced/rendered.yaml
```

For the advanced render in PowerShell:

```powershell
$env:CATALOG_API_KEY = 'example-api-key'
kube-app render examples/advanced/app.yaml -o examples/advanced/rendered.yaml
```

Omit `-o` to inspect output without replacing the checked-in file. These commands
render locally; they do not deploy to a cluster or invoke Helm.

The advanced application reads [config/catalog.properties](advanced/config/catalog.properties)
and [secrets/catalog-db.env](advanced/secrets/catalog-db.env). Paths resolve
relative to `app.yaml`, so its `config/` and `secrets/` references remain valid.
Validation checks the schema and references; rendering additionally reads files
and resolves environment variables.

The outputs use demonstration credentials and `CATALOG_API_KEY=example-api-key`.
Never commit real credentials or rendered secrets. Images, storage classes, and
the advanced service account are illustrative and must suit your cluster before
deployment.

After intentional example changes, regenerate the corresponding output and run
the [tests](../tests/README.md), which compare parsed YAML against these fixtures.
See [rendering semantics](../docs/RENDERING.md) for file formats and defaults.


Version 0.1.1 adds container ports, image pull policy, HTTP health probes,
and command/args. See [runtime configuration](../docs/RENDERING.md#runtime-configuration-v011).
