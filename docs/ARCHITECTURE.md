# Kube-App Architecture

## Purpose

Kube-App is a lightweight developer-facing abstraction for deploying applications to Kubernetes.

**Principle:** public YAML describes **application intent**, not Kubernetes implementation details.

Primary use is **CI/CD**; manual execution is mainly for testing.

## Flow

```text
app.yaml
  ↓
Application Model
  ↓
Validation + Defaults
  ↓
Renderer
  ↓
Kubernetes YAML
```

The Application Model must remain independent of the renderer.

## Public Schema

Do not expose Kubernetes CRD structure (`apiVersion`, `kind`, `metadata`, `spec`) in the public YAML.

Example:

```yaml
name: catalog

replicas: 3

containers:
  - name: catalog
    image: registry.example.com/catalog:1.4.2
```

## Progressive Capabilities

Use **one schema**. Basic, Medium and Advanced are progressively richer examples, not separate modes.

* **Basic:** name, replicas, containers/images, resources, service
* **Medium:** Basic + environment, configuration, secrets, storage, mounts, service options
* **Advanced:** Medium + multiple containers, init containers, service accounts, file-based configuration/secrets

`replicas` is a static replica count. Autoscaling is a separate future concept.

## Resource vs Consumption

Top-level resources define **what exists**.

Container/init-container fields define **how it is consumed**.

Example:

```yaml
storage:
  name: data
  size: 10Gi
  storageClass: fast
  accessModes:
    - ReadWriteOnce

containers:
  - name: app
    mounts:
      - storage: data
        path: /data
```

The same model applies to configuration and secrets.

## Configuration and Secrets

Both support inline data or files:

```yaml
configuration:
  - name: app-config
    data:
      APP_ENV: production

  - name: app-config-file
    file: config/app.properties
```

```yaml
secrets:
  - name: app-secret
    data:
      PASSWORD: ${DB_PASSWORD}

  - name: app-secret-file
    file: secrets/app.env
```

Files are read during rendering. CI/CD is the primary use case. Do not encourage committing real secrets.

## Storage

Kube-App generates a **PVC**, not a PV.

`storageClass` relies on Kubernetes dynamic provisioning.

## Services

Service configuration expresses application intent:

```yaml
service:
  type: LoadBalancer
  port: 8080
```

Kube-App generates selectors, labels and other Kubernetes implementation details.

For multiple containers:

```yaml
service:
  port: 8080
  container: catalog
```

## Kubernetes Boundary

Do not turn Kube-App into "Kubernetes YAML with different field names."

Only expose Kubernetes concepts when they represent a useful, common application-level requirement.

Kubernetes remains the escape hatch for advanced requirements.

## Renderer

Keep rendering separate from the model:

```text
Application Model
      ↓
Kubernetes Renderer
      ↓
Deployment / Service / ConfigMap / Secret / PVC / ...
```

Renderers should be deterministic and testable without a live Kubernetes cluster.

`kubeapp.renderers.Renderer[Output]` defines `render(application, base_dir=".")`.
Each backend chooses its output type; the contract does not require Kubernetes
resource dictionaries. Renderers consume validated `Application` objects without
mutating them and resolve file inputs relative to `base_dir`. Callers serialize
and write the result.

The CLI uses `KubernetesRenderer`, which delegates to the existing
`kubeapp.manifests` implementation and returns ordered resource dictionaries.
Existing manifest functions and legacy application support remain available.
The model imports no renderer code.

`HelmRenderer` implements `Renderer[dict[str, Any]]` and generates values for
the Basic and Medium examples, including inline configuration and Secret resources consumed as
environment variables. `configuration` and `secrets` values preserve declaration
order and Application-defined names. Secrets render as Opaque with `stringData`,
using the same inline substitution as configuration. `envFrom` places configuration
references before Secret references, preserving consumption order within each list.
Storage values create PVCs named `<application>-<storage>`, preserving size,
optional storageClass, and accessModes. Mounts produce `volumes` and `volumeMounts`:
configuration/Secret mounts are read-only, while storage mounts use the PVC with
default read-write access. Mount order is preserved, and repeated sources share
one volume identified by resource kind and name.
HTTP health intent maps to readinessProbe, livenessProbe, and startupProbe values.
Only declared probes render; numeric/named ports and model timing defaults are preserved.
Literal environment entries render as ordered `env` values. ClusterIP/LoadBalancer
Services preserve explicit numeric or named targetPort values. The actual Medium
example is tested end-to-end and compared semantically with KubernetesRenderer.
File-based configuration/Secrets and other unsupported Medium/Advanced capabilities
remain unsupported and fail explicitly. Helm template
execution in the application and CLI selection remain deferred. The chart consumes
`replicaCount`, `containerName`, `ports`, and `service.targetPort`, and honors
`service.enabled` and `serviceAccount.create` for Basic values.
The legacy Helm-values helper remains compatibility code,
sharing image-reference splitting with the new renderer.

## Development Rule

For every feature ask:

1. Is this an application requirement?
2. Is it common enough for the paved road?
3. Can an ordinary developer understand it?
4. Can the renderer translate it cleanly?
5. Does it keep the YAML simple?

Prefer:

```text
Model → Validation → Renderer → Tests → CLI
```

Make incremental changes and preserve the existing architecture.


Version 0.1.1 adds container ports, image pull policy, HTTP health probes,
and command/args. See [runtime configuration](../docs/RENDERING.md#runtime-configuration-v011).
