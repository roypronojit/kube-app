# Changelog

All notable changes to Kube-App are documented in this file.

Versions use Calendar Versioning (CalVer) in the `YYYY.MM.DD.PATCH` format.
Increment `PATCH` when more than one release is made on the same day.

## 2026.09.15.1 - [0.2.0]

### Added

- Basic Application-to-Helm-values translation owned by `HelmRenderer`, with
  static replicas, image/pull policy, container name/port, resource requests and
  limits, and ClusterIP service targeting. Unsupported capabilities fail explicitly.
- Focused tests for Basic values, image references, optional resources, application
  immutability, and rejection of unsupported capabilities. All 177 unittest tests pass.

### Changed

- Added a renderer-independent `Renderer[Output]` contract and a Kubernetes
  adapter over the existing manifest implementation; the CLI uses the adapter.
- Preserved the application schema, Kubernetes output, and existing manifest
  APIs. Helm template execution, chart alignment, and CLI renderer selection remain
  deferred. The legacy values helper reuses image splitting from `HelmRenderer`
  and preserves its existing output.
- Added renderer boundary tests for output parity, file resolution, model
  immutability, and legacy compatibility.

## 2026.09.14.2 - [0.1.1]

### Added

- Container HTTP readiness, liveness, and startup probes with timing validation.
- Named container ports and service targetPort selection.
- Container and init command/args overrides and imagePullPolicy.
- Runtime validation and rendering regression tests.

### Changed

- Replaced `src/kubeapp/models.py` with a `models/` package separating
  application validation, container runtime settings, configuration/storage,
  and shared types and validators.
- Replaced `src/kubeapp/manifests.py` with a `manifests/` package separating
  rendering orchestration, deployments, containers, supporting resources,
  and common helpers. Package exports preserve existing Python imports.
- Split `tests/test_models.py` and `tests/test_manifests.py` into
  `tests/model_tests/` and `tests/manifest_tests/`, grouped by responsibility
  with shared fixture helpers and standard unittest discovery.
- Updated source and test directory guides. The directory refactor preserves
  application schemas, rendered Kubernetes output, and test behavior;
  all 145 tests pass.
- Basic demonstrates ports and pull policy using unprivileged NGINX; Medium
  demonstrates health probes; Advanced demonstrates command/args.
- Regenerated all example manifests and updated runtime documentation.
- Updated Python package version to 0.1.1.

## 2026.09.14.1 - [0.1.0]

### Changed

- Grouped examples into `examples/basic/`, `examples/medium/`, and
  `examples/advanced/`, each containing `app.yaml` and `rendered.yaml`.
- Moved advanced configuration and secret files into the advanced example
  directory and removed the shared output directory.
- Added examples, source, and test guides; updated documentation and test
  fixture paths. Paths in older release entries describe the layout at release time.

## 2026.09.13.3 - [0.1.0]

### Added

- Application runtime model built around containers. `spec.containers` and
  `spec.initContainers` each take `name`, `image`, `environment`, `mounts`, and
  `resources`; container names must be unique across both lists.
- `environment` entries name exactly one source: a literal `value`, a `secret`
  (`name` plus `key`), or a `config` (`name` plus `key`). Numbers and booleans
  are accepted for `value` and passed through as strings.
- `mounts` entries name exactly one of `config`, `secret`, or `storage`, plus
  the `path` where the application expects it. A mount name shared by two
  containers becomes a single pod volume; reusing one name for two different
  sources is rejected.
- `spec.storage` entries with `size`, optional `storageClass`, and optional
  `accessModes` (default `ReadWriteOnce`). Each entry generates one
  PersistentVolumeClaim named `<application>-<storage>` and must be mounted by
  a container.
- `spec.service.type` accepting `ClusterIP` (default), `NodePort`, or
  `LoadBalancer`, and `spec.service.container` naming the container that
  receives traffic. Only that container is given the port.
- `spec.serviceAccount.name`, referencing an identity that already exists and
  rendering as `serviceAccountName`.
- Example `examples/advanced.yaml` and its generated manifests
  `output/advanced-manifest.yaml`.
- Model and renderer tests for containers, environment sources, mounts,
  storage, service types and targeting, init containers, service accounts, and
  an integration-style test over the advanced example.

### Changed

- `spec.image` is now the single-container shorthand and is mutually exclusive
  with `spec.containers`. The renderer builds the container from `spec.image`
  and `spec.resources`, naming it after the application, so existing
  applications render unchanged.
- Spec-level `resources` is rejected together with `containers`, so resources
  always belong to a named container.
- The Helm-values generator now fails with a clear error for applications that
  define `containers`, instead of failing on a missing image.

### Removed

- The map-shaped `spec.environment`, `spec.secrets`, `spec.configuration`, and
  `spec.storage` sections, and the `examples/configuration-and-storage.yaml`
  example. They could not express which consumption mechanism an application
  wanted, so they were replaced by the container model above before release.

### Notes

- The public application schema describes application intent. `secretKeyRef`,
  `configMapKeyRef`, volumes, volume mounts, claim names, and
  `serviceAccountName` exist only in the renderer.
- Secret and config providers and service accounts are referenced, never
  created. PersistentVolumeClaims are the only object kube-app owns; the
  backing PersistentVolume is left to dynamic provisioning.

### Pending

- The Helm-values generator only understands the single-image shorthand; the
  direct Kubernetes renderer implements the full runtime model.
- Containers cannot yet expose ports other than the one the Service targets.

## 2026.09.13.1 - [0.1.0]

### Added

- Distribution design requirement: development uses Python 3.11+, while future
  end-user releases will be standalone binaries that bundle runtime
  dependencies. PyInstaller will be evaluated after the core CLI, render
  functionality, and tests are stable.

## 2026.09.13.0 - [0.1.0]

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
