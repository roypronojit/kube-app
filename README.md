# Kube-App

> **Version:** 0.3.0 · **Release status:** Development Preview

A lightweight developer-facing abstraction for deploying standardized applications to Kubernetes without requiring application developers to manage Kubernetes primitives directly.

**One application specification. Deployment-native outputs.**

[Previous overview diagram (outdated)](docs/kube-app-0.2.0-overview.png): it shows the superseded Helm execution and shared-output architecture. Use the current text flow below.

## Vision

Kube-App provides a simple, declarative application specification that allows developers to describe **what their application needs**, while the platform translates that intent into Kubernetes manifests or Helm values.

The goal is to create a consistent developer experience while allowing platform teams to own Kubernetes implementation details, platform defaults, security standards, and operational conventions.

Over time, Kube-App aims to support the same application model across Kubernetes environments such as **Amazon EKS**, **Azure AKS**, and local development clusters.

---

## Why Kube-App?

Kubernetes provides a powerful application platform, but application developers often need to understand infrastructure concepts that are not directly related to their application.

A typical deployment may require developers to work with:

* Deployments
* Services
* ConfigMaps
* Secrets
* PersistentVolumeClaims
* ServiceAccounts
* labels and selectors
* volumes and volume mounts
* container resource requests and limits

Kube-App introduces an application-oriented layer above these primitives.

Instead of describing Kubernetes resources directly, developers describe application intent:

```yaml
name: hello-world

replicas: 2

containers:
  - name: hello-world
    image: nginxinc/nginx-unprivileged:1.27
    imagePullPolicy: IfNotPresent
    ports:
      - name: http
        port: 8080

    resources:
      cpu:
        min: 100m
        max: 500m
      memory:
        min: 128Mi
        max: 256Mi

service:
  port: 80
  targetPort: http
```

Kube-App validates the application definition, applies platform defaults, and generates the selected deployment-specific YAML.

The objective is **not** to hide Kubernetes completely. Kubernetes remains the escape hatch for requirements that do not belong in the platform's paved road.

---

## Core Concept

The public YAML describes **application intent**, not Kubernetes implementation details.

```text
app.yaml -> Parse / Validate -> Application Model
                                  |-- KubernetesRenderer -> Kubernetes manifests YAML
                                  `-- external chart inspection + HelmRenderer -> Helm values YAML
                                                                               + stderr diagnostics
```

The application model remains independent of the rendering implementation.

This allows Kube-App to evolve its Kubernetes implementation without requiring application developers to rewrite their application definitions.

For architectural details, see:

* [Architecture](docs/ARCHITECTURE.md)
* [Rendering semantics](docs/RENDERING.md)

---

# Quick Start

## Requirements

For standalone Linux use, see [Distribution](#distribution); no Python install is needed.
Development from source requires:

* Python 3.11 or later
* pip
* An existing chart directory for Helm values generation (no Helm executable required)

A Kubernetes cluster is **not required** to validate applications or render manifests.

## Install for development

From the repository root:

```sh
python -m pip install -e .
```

This installs the `kube-app` command.

## Validate an application

```sh
kube-app validate examples/basic/app.yaml
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

## Generate deployment-specific YAML

```sh
kube-app render examples/basic/app.yaml -f kubernetes -o kubernetes-manifests.yaml
kube-app render examples/basic/app.yaml -f helm -c charts/kube-app -o helm-values.yaml
kube-app render examples/basic/app.yaml -f h -c charts/kube-app -n preview > values.yaml
```

`charts/kube-app` is an explicit reference chart for these commands, not an implicit
requirement. The reference contract covers all three examples without mapping diagnostics.
Other charts' keys may differ; diagnostics flag mapping uncertainty.
The commands are also available as `python -m kubeapp`.

# Application Model

Kube-App uses **one application schema**.

Basic, medium, and advanced applications are progressively richer uses of the same model.
All three examples work unchanged with either renderer; renderer selection is a CLI option,
not part of the application YAML.

## Basic

A basic application can define:

* application name
* replicas
* containers
* images
* resources
* service

Example:

```yaml
name: hello-world

replicas: 2

containers:
  - name: hello-world
    image: nginxinc/nginx-unprivileged:1.27
    imagePullPolicy: IfNotPresent
    ports:
      - name: http
        port: 8080

    resources:
      cpu:
        min: 100m
        max: 500m
      memory:
        min: 128Mi
        max: 256Mi

service:
  port: 80
  targetPort: http
```

See [`examples/basic`](examples/basic/).

## Medium

A medium application builds on the same model with common runtime requirements such as:

* environment variables
* configuration
* secrets
* persistent storage
* mounts
* service options

See [`examples/medium`](examples/medium/).

## Advanced

An advanced application can additionally demonstrate capabilities such as:

* multiple containers
* init containers
* service accounts
* file-based configuration
* file-based secrets
* shared storage

See [`examples/advanced`](examples/advanced/).

For complete examples and regeneration instructions, see the [examples guide](examples/README.md).

---

# Resource Declaration and Consumption

Kube-App separates **resources that exist** from **how application components consume them**.

Top-level resources define what exists.

For example:

```yaml
storage:
  name: data
  size: 10Gi
  storageClass: fast
  accessModes:
    - ReadWriteOnce
```

A container can then consume that storage:

```yaml
containers:
  - name: catalog
    image: registry.example.com/catalog:1.4.2

    mounts:
      - storage: data
        path: /data
```

The same principle applies to configuration and secrets.

This keeps resource ownership separate from container-specific consumption.

---

# Configuration and Secrets

Configuration and secrets can be defined from inline data or files.

Example configuration:

```yaml
configuration:
  - name: catalog-config
    data:
      APP_ENV: production
      LOG_LEVEL: info
```

File-based configuration:

```yaml
configuration:
  - name: catalog-config
    file: config/catalog.properties
```

Secrets can follow the same pattern:

```yaml
secrets:
  - name: catalog-db
    file: secrets/catalog-db.env
```

Application components determine how those resources are consumed.

For example:

```yaml
containers:
  - name: catalog
    image: registry.example.com/catalog:1.4.2

    secrets:
      - name: catalog-db
        as: environment

    mounts:
      - configuration: catalog-config
        path: /etc/catalog
```

Files are resolved relative to the application definition during rendering.

The advanced example contains demonstration credentials only.

**Never commit real credentials, secret files, or rendered manifests containing real secret values.**

See [Rendering Semantics](docs/RENDERING.md) for details about file inputs and environment substitution.

---

# Storage

Kube-App models persistent application storage without requiring application developers to construct Kubernetes PersistentVolumeClaims directly.

Example:

```yaml
storage:
  name: data
  size: 10Gi
  storageClass: fast
  accessModes:
    - ReadWriteOnce
```

Kubernetes format renders a **PersistentVolumeClaim (PVC)**; Helm format emits storage values.

It does **not** create PersistentVolumes directly.

When a `storageClass` is specified, Kubernetes dynamic provisioning is expected to provide the underlying PersistentVolume.

---

# Services

Applications can expose a service with a small application-level definition:

```yaml
service:
  port: 8080
```

Supported Service types are `ClusterIP`, `NodePort` and `LoadBalancer` in both
Kubernetes manifests and Helm values. NodePort uses automatic Kubernetes allocation;
explicit nodePort numbers and additional Service networking options are not exposed.

Service options can also be specified:

```yaml
service:
  type: LoadBalancer
  port: 8080
```

When an application contains multiple containers, the service can identify the target container:

```yaml
service:
  type: LoadBalancer
  port: 8080
  container: catalog
```

Kube-App owns the Kubernetes labels, selectors, and other implementation details required to connect the Service to the workload.

---

# Generated Kubernetes Resources

Depending on the application definition, Kube-App can currently render resources including:

* Deployment
* Service
* ConfigMap
* Secret
* PersistentVolumeClaim

Additional workload behavior is generated from the application model, including:

* multiple containers
* init containers
* environment variables
* resource requests and limits
* configuration mounts
* secret mounts
* persistent storage mounts
* service account references

Each example retains app.yaml and separate kubernetes-manifests.yaml and
helm-values.yaml artifacts. See the [examples guide](examples/README.md).

# Testing

The test suite uses Python's standard-library `unittest` framework.

Run the complete suite:

```sh
python -m unittest discover -s tests -v
```

The tests cover:

* application model validation
* defaults and constraints
* application intent validation
* configuration and secret references
* storage and mounts
* services
* multiple containers
* init containers
* manifest generation
* CLI behavior
* example output comparisons
* compatibility behavior

No Kubernetes cluster is required. Optional internal reference-chart tests require Helm
and skip when unavailable; public CLI values-generation tests do not require Helm.

See the [test guide](tests/README.md) for details.

---

# Current Architecture

Kube-App separates the developer-facing application contract from validation and Kubernetes rendering.

[Previous architecture diagram (outdated)](docs/kube-app-0.2.0-architecture.png): replacement is pending separate review; the image is not the current CLI contract.

The key implementation rule is:

> **The application model must remain independent of the renderer.**

Both outputs consume the same validated Application. KubernetesRenderer emits resources;
HelmRenderer emits values, with external-chart inspection and stderr diagnostics.
See [Architecture](docs/ARCHITECTURE.md) for implementation boundaries and
[Rendering](docs/RENDERING.md) for current Helm translation limits.

The bundled chart remains a useful reference and internal test fixture. The active CLI
uses only the chart explicitly supplied with --chart and never executes Helm.

# Distribution

v0.3.0 adds a standalone Linux x86_64 executable containing the Python runtime and
application dependencies. Users need no host Python, pip, virtualenv or Helm for
validation or generation. app.yaml, referenced files and supplied charts remain external.

Download the versioned binary and SHA256 file from a published GitHub Release,
verify the checksum, then install the executable as `kube-app`. Official builds
use Ubuntu 22.04 (glibc 2.35 baseline); Alpine/musl and other CPU architectures are
not supported. One-file extraction requires a suitable writable temporary directory.

See [standalone installation, local builds and release gates](docs/DISTRIBUTION.md)
for exact commands and runtime constraints. PR/branch CI runs tests, builds and
smokes the real executable without publishing; matching version tags trigger the
same gates followed by a binary/checksum GitHub Release. No release is created by
ordinary CI or by local build commands.

# Roadmap

Kube-App is intentionally being developed incrementally.

## v0.1 — Core Application Abstraction

Implemented foundation:

* developer-facing application schema
* typed application model
* validation and defaults
* direct Kubernetes manifest rendering
* Deployment and Service generation
* configuration and secrets
* persistent storage
* multiple containers
* init containers
* service account references
* deterministic examples
* automated tests

## v0.2.0 ? Deployment-native outputs

* Kubernetes manifests or Helm values from one application specification
* Explicit external-chart inspection, declared value contracts and non-fatal diagnostics
* Name overrides, separate YAML/diagnostic streams and preserved output on failure

## v0.3.0 Standalone Linux packaging

* One-file Linux x86_64 executable with bundled runtime dependencies
* PR/branch build and packaged smoke gates
* Tag-driven binary and SHA256 publication after verification

## Platform Defaults and Security

The renderer does not inject pod or container security contexts that are absent
from `app.yaml`. The public schema currently has no security context fields.

Container-level HTTP readiness, liveness, and startup probes are configured under
`health`. Container `ports`, `imagePullPolicy`, and `command` / `args` are also
supported. See [runtime configuration](docs/RENDERING.md#runtime-configuration-v011)
for syntax, defaults, validation, and compatibility details.

Rollout strategies and disruption protection remain future work.

## Policy as Code

Kube-App may integrate with policy engines such as **Kyverno** for cluster-level governance.

The architectural boundary is:

> **Kube-App validates what an application specification means; cluster policy determines whether the resulting workload is allowed on the platform.**

## GitOps

Future integration with tools such as **Argo CD** can provide GitOps-based delivery.

Kube-App should integrate with established GitOps tooling rather than attempting to replace it.

## Networking

Future platform capabilities may explore **Cilium** and Kubernetes networking policy while keeping the developer-facing model application-oriented.

## Multi-Cloud Kubernetes

The application model should remain largely independent of the Kubernetes distribution.

Target environments may include:

* Amazon EKS
* Azure AKS
* local Kubernetes environments

Cloud-specific implementation should remain behind the platform abstraction wherever practical.

## Observability

Observability is deliberately decoupled from the core application model until the target platform stack is established.

Potential integrations may include:

* OpenTelemetry
* Prometheus
* Grafana
* Azure Monitor
* other platform-owned observability systems

The application contract should remain stable even if the underlying observability implementation changes.

---

# Architectural Principles

## 1. Developer Simplicity

Application developers should describe application requirements rather than Kubernetes implementation details.

## 2. Progressive Complexity

Simple applications should remain simple.

More advanced applications can opt into additional capabilities without requiring a separate schema or mode.

## 3. Platform-Owned Standards

Platform teams own defaults, governance, security standards, and infrastructure implementation.

## 4. Separation of Concerns

Application intent, validation, rendering, policy enforcement, GitOps, networking, and infrastructure should remain distinct concerns.

## 5. Kubernetes Native

Kube-App should work with Kubernetes and cloud-native technologies rather than unnecessarily replacing them.

## 6. Cloud Agnostic Where Practical

The developer-facing application model should not depend on whether the workload ultimately runs on EKS, AKS, or another Kubernetes distribution.

## 7. Don't Reinvent Mature Tools

Kube-App should provide the missing developer/platform abstraction while relying on established tools for capabilities they already solve well.

## 8. Kubernetes as the Escape Hatch

Kube-App should provide a useful paved road, not attempt to model every Kubernetes capability.

Requirements outside that paved road can continue to use Kubernetes directly.

---

# Repository Structure

```text
kubeApp/
├── src/
│   ├── README.md
│   └── kubeapp/
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli.py
│       ├── parser.py
│       ├── models/
│       ├── manifests/
│       ├── renderers/
│       └── generators.py
│
├── examples/
│   ├── README.md
│   ├── basic/
│   ├── medium/
│   └── advanced/
│
├── tests/
│   ├── README.md
│   ├── cli_tests/
│   ├── model_tests/
│   └── manifest_tests/
│
├── docs/
│   ├── ARCHITECTURE.md
│   ├── RENDERING.md
│   ├── kube-app-0.2.0-architecture.png
│   └── kube-app-0.2.0-overview.png
│
├── charts/
│   └── kube-app/
│
├── pyproject.toml
├── CHANGELOG.md
└── README.md
```

Directory-specific documentation:

* [Architecture](docs/ARCHITECTURE.md)
* [Rendering semantics](docs/RENDERING.md)
* [Examples](examples/README.md)
* [Source guide](src/README.md)
* [Test guide](tests/README.md)

---

# Development Principles

When considering a new kube-app capability, ask:

1. Is this an application requirement?
2. Is it common enough to belong on the paved road?
3. Can an ordinary application developer understand it?
4. Can the renderer translate it cleanly?
5. Does it keep the public YAML simpler than the Kubernetes resources it replaces?

The preferred development flow is:

```text
Application Model
       ↓
Validation
       ↓
Renderer
       ↓
Tests
       ↓
CLI
```

Changes should remain incremental and preserve separation between the application model and rendering implementation.

---

# Project Status

Kube-App is currently a **development preview**.

The `0.x` releases should be considered experimental. The public application schema may evolve as the project gains capabilities and real-world usage.

A future `1.0.0` release would indicate that the core developer-facing application contract is considered stable enough for broader compatibility expectations.

---

# Project Philosophy

Kube-App is built around a simple question:

> **Can we make Kubernetes easier for application developers while giving platform teams stronger control over standards, security, and operations?**

The objective is not to build another Helm, another GitOps engine, or another Kubernetes abstraction for its own sake.

The objective is to explore what a **developer-friendly, platform-owned Kubernetes experience** can look like while building on existing cloud-native technologies.
