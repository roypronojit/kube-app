# Kube-App

> **Version:**  - 0.1.0 · **Release status:** Private Preview

A lightweight developer-facing abstraction for deploying standardized applications to Kubernetes without requiring developers to manage Kubernetes primitives directly.

## Vision

Kube-App aims to provide a simple, declarative application specification that allows developers to describe **what their application needs**, while the platform handles the underlying Kubernetes implementation, security defaults, operational standards, and deployment mechanisms.

The long-term goal is to provide a consistent developer experience across Kubernetes platforms such as **Amazon EKS and Azure AKS**, while allowing platform teams to evolve the underlying implementation independently.

---

## Core Concept

The public YAML describes application intent. Kube-App validates the model,
applies defaults, and renders Kubernetes manifests directly.

See [the architecture](docs/ARCHITECTURE.md) and
[rendering semantics](docs/RENDERING.md) for the schema, defaults, file inputs,
and environment substitution.

## Usage

Use Python 3.11 or later:

```sh
python -m pip install -e .
kube-app validate examples/medium/app.yaml
kube-app render examples/medium/app.yaml -o examples/medium/rendered.yaml
```

Omit `-o` to write Kubernetes YAML to standard output. Basic, medium, and
advanced are progressively richer examples of one flat schema:

```yaml
name: hello-world
replicas: 2
containers:
  - name: hello-world
    image: nginx:1.27
    resources:
      cpu:
        min: 100m
        max: 500m
      memory:
        min: 128Mi
        max: 256Mi
service:
  port: 80
```

Top-level configuration, secrets, and storage define resources; container and
init-container references define how they are consumed. `serviceAccount`
references an existing account. Autoscaling is deferred.

Generated manifests live beside each application in [examples](examples/README.md). The advanced example's output
uses `CATALOG_API_KEY=example-api-key` and demonstration database credentials.
Never commit real credentials or manifests containing real secrets.

See [examples](examples/README.md), [source guide](src/README.md), and [test guide](tests/README.md) for directory-specific workflows.

Run all tests:

```sh
python -m unittest discover -s tests -v
```

### Helm status: TBD

The chart is present and can be checked with `helm lint charts/kube-app`, but
the CLI does not yet invoke Helm or render Kubernetes manifests through Helm.
Helm integration, including `helm template` and release installation, remains
pending.

### Distribution requirement: TBD

Development uses Python 3.11 or later. End users, however, should use
`kube-app` as a normal standalone CLI and must not need to install Python,
Pydantic, PyYAML, or other runtime dependencies.

After the core CLI, render functionality, and tests are stable, the project
will distribute standalone binaries for major platforms. PyInstaller is the
initial packaging option to evaluate. Packaging is intentionally deferred and
does not change the current Python development workflow.

---

# Development Roadmap

The phases below record the original roadmap, including the previous CRD-style
schema and Helm-first plan. Current behavior and schema are documented above
and in `docs/ARCHITECTURE.md`; autoscaling and Helm remain future work.

## Phase 1 — Application Abstraction

Build the minimal developer-facing abstraction.

### Goals

* Define an application specification
* Parse and validate `app.yaml`
* Create a typed internal application model
* Apply sensible platform defaults
* Generate Helm values
* Render Kubernetes manifests through Helm

### Initial developer experience

```bash
kube-app validate app.yaml
kube-app render app.yaml
```

### Example

```yaml
apiVersion: kubeapp.dev/v1alpha1
kind: Application

metadata:
  name: hello-world

spec:
  image: nginx:1.27

  service:
    port: 80

  resources:
    requests:
      cpu: 100m
      memory: 128Mi
    limits:
      cpu: 500m
      memory: 256Mi

  scaling:
    minReplicas: 2
    maxReplicas: 5
```

### Initial generated resources

* Deployment
* Service
* HPA

---

# Phase 2 — Platform Defaults & Security

Introduce opinionated platform defaults so developers don't need to configure common Kubernetes operational and security settings.

### Potential defaults

* Non-root containers
* `allowPrivilegeEscalation: false`
* Dropped Linux capabilities where appropriate
* Seccomp profile
* Resource requests and limits
* Readiness probes
* Liveness probes
* Standard labels
* ServiceAccount
* Rolling update strategy
* PodDisruptionBudget where appropriate

The platform should be **secure and operationally sound by default**, while still providing controlled escape hatches for legitimate application requirements.

---

# Phase 3 — Validation & Testing

Separate application specification validation from cluster-level policy enforcement.

### Application validation

```text
app.yaml
   │
   ▼
Schema validation
   │
   ├── Required fields
   ├── Valid values
   ├── Resource quantities
   ├── Scaling configuration
   └── API version compatibility
```

### Testing

Build automated tests for:

* Application parsing
* Schema validation
* Default values
* Invalid configurations
* Helm values generation
* Kubernetes manifest generation
* Security defaults

Add CI to perform:

```text
Commit
  │
  ├── Lint
  ├── Unit tests
  ├── Build
  └── Package
```

---

# Phase 4 — Policy as Code

Integrate **Kyverno** for cluster-level governance.

The application platform should not attempt to implement its own Kubernetes policy engine.

Instead:

```text
Developer
    │
 app.yaml
    ▼
kube-app
    │
    ▼
Helm
    │
    ▼
Kubernetes
    │
    ▼
Kyverno
```

### Example policies

* Required labels
* Security context requirements
* Resource requirements
* Image tag requirements
* Restricted workload configurations
* Platform-specific governance rules

The architectural distinction is:

> **Kube-App validates what an application specification means; Kyverno determines whether a resulting workload is allowed on the platform.**

---

# Phase 5 — GitOps Integration

Integrate with **Argo CD** to support GitOps-based deployment.

```text
Developer
    │
 app.yaml
    ▼
   Git
    │
    ▼
 Argo CD
    │
    ▼
 kube-app / Helm
    │
    ▼
Kubernetes
```

Kube-App should integrate with Argo CD rather than attempting to replace it.

The goal is to demonstrate how a developer-facing platform abstraction can work with existing cloud-native delivery tooling.

---

# Phase 6 — Kubernetes Networking

Explore integration with **Cilium** for Kubernetes networking and security.

Potential capabilities include:

* NetworkPolicy
* CiliumNetworkPolicy
* Application-level network controls
* Service-to-service communication policies
* Network visibility

Example:

```text
Frontend
    │
    │ allowed
    ▼
Backend
    │
    │ allowed
    ▼
Database
```

The platform should expose simple application-level concepts while the platform team owns the underlying networking implementation.

---

# Phase 7 — Multi-Cloud Kubernetes

Evaluate the platform against multiple Kubernetes environments.

Target environments:

* Amazon EKS
* Azure AKS
* Local Kubernetes for development

The developer specification should remain largely cloud-agnostic:

```text
                 app.yaml
                    │
             ┌──────┴──────┐
             ▼             ▼
            EKS           AKS
             │             │
        Kubernetes    Kubernetes
```

Cloud-specific implementation should remain behind the platform abstraction wherever practical.

---

# Phase 8 — Observability

Observability will remain deliberately decoupled from the core platform until the target organizational stack is established.

Potential integrations may include:

* Prometheus
* OpenTelemetry
* Azure Monitor
* Log Analytics
* Grafana
* Microsoft Defender

The goal is to keep the developer-facing application specification stable even if the underlying observability implementation changes.

For example:

```yaml
observability:
  enabled: true
```

The platform should determine how that requirement is implemented.

---

# Architectural Principles

## 1. Developer Simplicity

Developers should describe application intent rather than Kubernetes implementation details.

## 2. Secure by Default

Common security and operational requirements should be provided automatically.

## 3. Platform-Owned Standards

The platform team owns defaults, governance, policies, and infrastructure.

## 4. Kubernetes Native

Kube-App should integrate with Kubernetes-native and CNCF technologies rather than unnecessarily replacing them.

## 5. Separation of Concerns

```text
Kube-App
    │
    ├── Developer experience
    ├── Application specification
    └── Platform defaults

Helm
    │
    └── Kubernetes resource templating

Argo CD
    │
    └── GitOps delivery

Kyverno
    │
    └── Policy enforcement

Cilium
    │
    └── Networking and network security
```

## 6. Cloud Agnostic Where Practical

The developer experience should not depend on whether the workload ultimately runs on EKS, AKS, or another Kubernetes distribution.

## 7. Don't Reinvent Mature Tools

Kube-App should provide the missing developer/platform abstraction while leveraging existing technologies for their intended purposes.

---

# Repository Structure

```text
kubeApp/
|-- src/
|   |-- README.md
|   `-- kubeapp/          # CLI, models, parser, manifests, legacy generator
|-- charts/kube-app/      # Helm chart; CLI integration deferred
|-- examples/
|   |-- README.md
|   |-- basic/
|   |   |-- app.yaml
|   |   `-- rendered.yaml
|   |-- medium/
|   |   |-- app.yaml
|   |   `-- rendered.yaml
|   `-- advanced/
|       |-- app.yaml
|       |-- rendered.yaml
|       |-- config/catalog.properties
|       `-- secrets/catalog-db.env
|-- tests/
|   |-- README.md
|   |-- test_cli.py
|   |-- test_intent.py
|   |-- test_models.py
|   |-- test_manifests.py
|   `-- test_generators.py
|-- docs/
|   |-- ARCHITECTURE.md
|   `-- RENDERING.md
|-- pyproject.toml
|-- README.md
|-- CHANGELOG.md
`-- CODEX_CONTEXT.md
```

---

# First Milestone

The first milestone intentionally remains small.

### Target

```text
app.yaml
    │
    ▼
Pydantic model
    │
    ▼
Validation
    │
    ▼
Helm values
    │
    ▼
Helm chart
    │
    ▼
Kubernetes manifests
```

A successful first milestone should allow:

```bash
kube-app validate examples/basic/app.yaml
kube-app render examples/basic/app.yaml
```

and produce valid Kubernetes resources through the project's Helm chart.

### Not included in V1

* Argo CD
* Kyverno
* Cilium
* Cloud APIs
* Web UI
* Database
* Kubernetes operator/controller
* Multi-cluster management

These will only be introduced after the core abstraction is stable.

---

# Long-Term Architecture

```text
                         Developer
                             │
                             │ app.yaml
                             ▼
                    ┌─────────────────┐
                    │    Kube-App     │
                    │                 │
                    │ Developer       │
                    │ Abstraction     │
                    └────────┬────────┘
                             │
                             ▼
                           Helm
                             │
                 ┌───────────┼───────────┐
                 │           │           │
              Kyverno      Argo CD     Cilium
              Policy       GitOps      Network
                 │           │           │
                 └───────────┼───────────┘
                             ▼
                        Kubernetes
                         /       \
                        /         \
                      EKS         AKS
```

---

# Project Philosophy

The project is intentionally designed around a simple question:

> **Can we make Kubernetes easier for application developers while giving platform teams stronger control over standards, security, and operations?**

The objective is not to build another Helm, another GitOps engine, or another Kubernetes abstraction for its own sake.

The objective is to explore what a **developer-friendly, policy-driven Kubernetes platform experience** can look like while building on existing cloud-native technologies.
