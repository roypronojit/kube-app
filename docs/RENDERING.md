# Rendering applications

The public schema is described in [ARCHITECTURE.md](ARCHITECTURE.md). The
`basic`, `medium`, and `advanced` examples use the same schema. `render`
produces final Kubernetes YAML through KubernetesRenderer (the default) or
HelmRenderer followed by `helm template`. Select with `--renderer` / `-r`:
`kubernetes`, `k8s`, `k` or `helm`, `h`. Only the Helm backend requires Helm on `PATH`.

```sh
kube-app validate examples/medium/app.yaml
kube-app render examples/medium/app.yaml -o examples/medium/rendered.yaml
kube-app render examples/medium/app.yaml -r helm
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