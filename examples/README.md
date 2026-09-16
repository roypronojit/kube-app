# Examples: two deployment workflows

One application specification. Deployment-native outputs.

| Example | Developer input | Kubernetes output | Helm output |
| --- | --- | --- | --- |
| Basic | [app.yaml](basic/app.yaml) | [manifests](basic/kubernetes-manifests.yaml) | [values](basic/helm-values.yaml) |
| Medium | [app.yaml](medium/app.yaml) | [manifests](medium/kubernetes-manifests.yaml) | [values](medium/helm-values.yaml) |
| Advanced | [app.yaml](advanced/app.yaml) | [manifests](advanced/kubernetes-manifests.yaml) | [values](advanced/helm-values.yaml) |

Basic demonstrates one container, resources and a Service. Medium adds inline
configuration/secrets, probes and storage. Advanced adds multiple/init containers,
file inputs, command/args and an existing service account. All use the same schema.

From the repository root after installing kube-app:

```sh
export CATALOG_API_KEY=example-api-key
for example in basic medium advanced; do
  kube-app validate examples/$example/app.yaml
  kube-app render examples/$example/app.yaml -f kubernetes -o examples/$example/kubernetes-manifests.yaml
  kube-app render examples/$example/app.yaml -f helm -c charts/kube-app -o examples/$example/helm-values.yaml
done
```

In PowerShell set `$env:CATALOG_API_KEY = 'example-api-key'` and run each render
command with the desired example name. Omit -o for stdout; Helm diagnostics remain
on stderr. The explicit charts/kube-app reference is compatible with the existing
values layout. Its defaults and schema declare the supported generated paths, so
the three examples produce no mapping warnings or notes. Other charts can report
contract mismatches; diagnostics never remove values or imply failed resource creation.
Review values against your own chart before using them in a separate Helm workflow.
No Helm executable or cluster is required for generation; kube-app never templates
or installs the supplied chart and does not modify it.

Advanced reads [configuration](advanced/config/catalog.properties) and
[demonstration database credentials](advanced/secrets/catalog-db.env) relative to
app.yaml even when invoked from another directory. All committed outputs use
`change-me` / `example-api-key` placeholders. Never commit real resolved secrets.
Images, storage classes and service-account identities are illustrative.

`-f k8s`, `-f k` and the omitted format use Kubernetes. `-f h` selects Helm and
requires -c/--chart. `-n/--name` overrides application identity while preserving
explicit resource/container names. See [rendering semantics](../docs/RENDERING.md)
for the contract, diagnostics, failure behavior and translation limits.
