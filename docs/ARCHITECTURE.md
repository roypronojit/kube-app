# Kube-App Architecture

## Purpose

Kube-App is a lightweight developer-facing abstraction for deploying applications to Kubernetes.

**Principle:** public YAML describes **application intent**, not Kubernetes implementation details.

Primary use is **CI/CD**; manual execution is mainly for testing.

## Flow

```text
app.yaml -> Parse / Validate -> Application Model
                                  |-- KubernetesRenderer -> Kubernetes manifests YAML
                                  `-- external chart inspection + HelmRenderer -> Helm values YAML
                                                                               + stderr diagnostics
```

The Application Model remains independent of the selected output format.

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

## Implementation boundaries

`Renderer[Output]` accepts a validated Application and base_dir. KubernetesRenderer
returns resource dictionaries; HelmRenderer returns the existing values dictionary.
The CLI coordinates chart_inspection, value_mapping and diagnostics, then serializes
the deployment-specific result. The model imports no renderer or chart code.

Helm values retain name, replicaCount, image/container settings, ordered containers
and initContainers, resources, probes, service configuration, configuration/secrets,
storage, volumes and mounts. File parsing and substitution occur during translation.
Single-container values use top-level fields; multiple containers use a containers list.
The Helm translator supports ClusterIP, NodePort and LoadBalancer Service types.
NodePort uses automatic Kubernetes port allocation; no explicit nodePort field is exposed.
Digest image references, init ports and multiple/non-TCP ports remain unsupported.
ExternalName, headless Services, explicit nodePort allocation, multiple Service ports
and additional Service networking options are outside the current public model.

charts/kube-app is a reference chart and internal template-test target, not a required
implicit CLI dependency. Internal reference-chart resource comparisons do not imply
that public Kubernetes and Helm outputs have the same type. Legacy helper APIs remain
for compatibility; no chart is installed and no resources are created by generation.

## Diagram status

The existing [overview PNG](kube-app-0.2.0-overview.png) and
[architecture PNG](kube-app-0.2.0-architecture.png) are outdated illustrations of the
previous architecture, including old flags, Helm execution and shared manifest output.
They are not the v0.2.0 contract. The text flow above is authoritative; image replacement
is pending a separate review.

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
