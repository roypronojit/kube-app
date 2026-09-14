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

Helm may become another renderer later; it must not define the application model.

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
