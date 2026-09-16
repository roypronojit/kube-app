# Rendering applications

```text
app.yaml -> Parse / Validate -> Application Model
                                  |-- KubernetesRenderer -> Kubernetes manifests YAML
                                  `-- external chart inspection + HelmRenderer -> Helm values YAML
                                                                               + stderr diagnostics
```

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

## Kubernetes resources and shared intent

`replicas` defaults to 1 and accepts 0 to stop the workload. Resource `min`
values become requests; `max` values become limits. Service type defaults to
ClusterIP. A service with multiple application containers requires an explicit
`container` target. Init containers cannot be service targets.

In Kubernetes output, top-level configuration and secrets produce ConfigMaps and Opaque Secrets.
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
CATALOG_API_KEY=example-api-key kube-app render examples/advanced/app.yaml -o examples/advanced/kubernetes-manifests.yaml
```

PowerShell equivalent:

```powershell
$env:CATALOG_API_KEY = 'example-api-key'
kube-app render examples/advanced/app.yaml -o examples/advanced/kubernetes-manifests.yaml
```

Rendered Secret manifests and Helm values contain sensitive values. Do not commit real secrets
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

## Runtime configuration (v0.1.1)

Each application container supports named ports, an image pull policy, process
overrides, and HTTP health checks:

```yaml
containers:
  - name: app
    image: registry.example.com/app:1
    imagePullPolicy: IfNotPresent
    ports:
      - name: http
        port: 8080
        protocol: TCP
    command: ["/app/server"]
    args: ["--port", "8080"]
    healthChecks:
      ready:
        path: /health/ready
        port: http
      live:
        path: /health/live
        port: http
        initialDelaySeconds: 10
      startup:
        path: /health/startup
        port: http
        failureThreshold: 30
service:
  port: 80
  targetPort: http
```

Ports render as `containerPort` entries even without a service. Names are unique
within each container, start with a lowercase letter, contain lowercase letters,
digits or hyphens, end with a letter or digit, and have at most 15 characters.
Port numbers are integers from 1 through 65535. Protocol defaults to TCP; UDP
and SCTP are also accepted. Duplicate number/protocol pairs are rejected.

Services remain TCP. `service.targetPort` accepts a declared TCP port name or
number. If omitted, it selects the sole declared TCP container port; multiple
TCP ports require an explicit target. With no declared ports it defaults to
`service.port`. When the selected container declares
ports, the target must match one of them. Without declared ports, a numeric
target is inferred as a container port named `http`, preserving existing
service-only inputs. A named target requires an explicit declaration.
`service.container` selects the target when there are multiple containers.

`imagePullPolicy` accepts `Always`, `IfNotPresent` (the platform default,
including untagged and latest images), or `Never`. `command` and `args` are
optional nonempty string lists; omitted fields retain image defaults. The
command executable cannot be blank. Empty individual arguments are allowed.
Values are passed through without shell execution or environment substitution
by Kube-App; request a shell explicitly if needed.

`healthChecks` (also accepted as `healthCheck` or the original `health`) uses
`ready`, `live`, and `startup`; `readiness` and `liveness` remain accepted aliases.
`frequencySeconds` maps to Kubernetes `periodSeconds`; the original
`periodSeconds` spelling is also accepted.

Health checks are optional and render to `readinessProbe`, `livenessProbe`,
and `startupProbe` with `httpGet`. A probe requires an absolute HTTP path and
a numeric port or a declared TCP port name on that container. Numeric probe
ports need no port declaration. Timing defaults are `initialDelaySeconds: 0`,
`periodSeconds: 10`, `timeoutSeconds: 1`, `failureThreshold: 3`, and
`successThreshold: 1`. Values must be integers; only initial delay may be zero.
Liveness and startup success thresholds must equal 1. An empty `health` block
is rejected. Init containers support ports, pull policy, command and args, but
cannot define health probes. HTTP checks are the supported probe type in this
release. See [Kubernetes probe semantics](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-probes/).

### Security context

The renderer does not inject pod or container `securityContext` settings.
The public schema currently has no security context fields, so none are emitted
for application or init containers.

Basic uses unprivileged NGINX listening on 8080 behind service port 80. Medium
and Advanced use illustrative application images; supply compatible images and
implement the Medium health endpoints before deploying. Advanced command paths
must exist in the supplied images. The legacy Python model and its renderer
retain their previous behavior; these additions apply to the public flat schema.
## Helm translation limits

The current translator rejects digest images, init ports and multiple/non-TCP container
ports. Supported Service types are ClusterIP, NodePort and LoadBalancer. NodePort
leaves port allocation to Kubernetes. ExternalName, headless Services, explicit
nodePort allocation, multiple Service ports and additional Service networking
options are not exposed by the model. Other runtime details above
describe Kubernetes behavior; Helm uses its existing values layout without arbitrary
external-chart adaptation. See the [example workflows](../examples/README.md).
