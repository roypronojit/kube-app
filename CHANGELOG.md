# Changelog

All notable changes to Kube-App are documented in this file.

Versions use Calendar Versioning (CalVer) in the `YYYY.MM.DD.PATCH` format.
Increment `PATCH` when more than one release is made on the same day.

## 2026.09.13.3

### Added

- Application `spec.environment`: plain key/value settings delivered to the
  container as environment variables. Numbers and booleans are accepted and
  passed through as strings.
- Application `spec.secrets`: maps an environment-variable name to the name of
  a sensitive-value provider the platform team manages.
- Application `spec.configuration`: maps an environment-variable name to the
  name of a shared-configuration provider the platform team manages.
- Application `spec.storage`: persistent application data, keyed by name, with
  a `size` and a `path`.
- Kubernetes renderer translation of the above into container `env`,
  `env.valueFrom.secretKeyRef`, `env.valueFrom.configMapKeyRef`,
  PersistentVolumeClaims, pod volumes, and container volume mounts, emitted in
  the deterministic order PersistentVolumeClaim, Deployment, Service.
- Example `examples/configuration-and-storage.yaml` and its generated manifest
  `output/configuration-and-storage-manifest.yaml`.
- Model and renderer tests for environment settings, secret and shared
  configuration, single and multiple storage entries, invalid names, sizes and
  paths, and a complete application using all four sections.

### Notes

- The public application schema describes application intent. Kubernetes
  concepts — `secretKeyRef`, `configMapKeyRef`, volumes, volume mounts, access
  modes, claim names — exist only in the renderer.
- A provided value is read under the key matching the environment-variable
  name, so `DATABASE_URL: catalog-db` expects a `DATABASE_URL` entry in the
  `catalog-db` provider.
- Secret and configuration providers are referenced, never created.
  PersistentVolumeClaims are the only new object kube-app owns; their access
  mode is a platform default.
- Applications that do not use the new sections render exactly the same
  Deployment and Service as before.

### Pending

- The Helm-values generator does not yet map `environment`, `secrets`,
  `configuration`, or `storage`; the direct Kubernetes renderer is the only
  implementation of these capabilities.

## 2026.09.13.1

### Added

- Distribution design requirement: development uses Python 3.11+, while future
  end-user releases will be standalone binaries that bundle runtime
  dependencies. PyInstaller will be evaluated after the core CLI, render
  functionality, and tests are stable.

## 2026.09.13.0

### Added

- Pydantic application model and YAML parsing/validation for the
  `kubeapp.dev/v1alpha1` `Application` resource.
- Helm-values generator that maps application name, image, service port,
  resources, and scaling bounds to a plain Python dictionary.
- Direct Kubernetes-manifest generator for a Deployment and optional ClusterIP
  Service.
- Generated example manifest at `output/basic-manifest.yaml` for
  `examples/basic.yaml`.
- Unit tests for Helm-values and Kubernetes-manifest generation.
- README usage instructions for validation, values generation, manifest tests,
  and optional cluster dry-run validation.
- Renamed stale Helm helper references from `kube-app-scaffold.*` to
  `kube-app.*`.
- Made the Helm chart notes template safe when `httpRoute` is not configured.

### Pending

- Helm CLI integration (`helm template` and release installation).
- HorizontalPodAutoscaler and VerticalPodAutoscaler support.
- Additional service types, ConfigMaps, Secrets, and ServiceAccounts in the
  application schema and direct manifest generator.
