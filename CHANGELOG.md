# Changelog

All notable changes to Kube-App are documented in this file.

Versions use Calendar Versioning (CalVer) in the `YYYY.MM.DD.PATCH` format.
Increment `PATCH` when more than one release is made on the same day.
For v0.2.0 development, entries are split by implementation step; the daily suffix orders
these checkpoints and does not indicate a separately published release.

## 2026.09.16.3 - [0.2.0]

- Step 18: added explicit service.container resolution using the validated reference.
  Default targetPort and declared-port checks now use the selected application
  container; explicit named/numeric targets and absent-selection behavior are preserved.
- Added values/chart tests for non-first container selection, independent ports,
  named/numeric targets, immutability, and rejection of selected containers without ports.
- Validation: 211 unittest tests passed, including Basic/Medium equivalence;
  Helm lint passed. No CLI changes or full Advanced equivalence work.
- The unchanged Advanced example remains blocked only by Service targeting
  without a declared container port; fallback targeting remains unsupported.

## 2026.09.16.2 - [0.2.0]

- Step 17: added Application serviceAccount references through Helm values with
  create=false. Deployment serviceAccountName preserves the exact declared name;
  quoting prevents YAML scalar coercion. No ServiceAccount resource is created.
- Preserved the default service account behavior when absent. Added values/chart
  tests for exact names, omission, multiple/init containers, and model immutability.
- Validation: 209 unittest tests passed, including Basic/Medium equivalence;
  Helm lint passed. No CLI changes or full Advanced equivalence work.
- Advanced remains blocked by explicit service.container selection and Service
  targeting without a declared container port.

## 2026.09.16.1 - [0.2.0]

- Step 16: added command/args translation and Deployment rendering for application
  and init containers. Lists preserve values and order exactly and are omitted
  when undeclared; shared translation copies lists without mutating the model.
- Added values/chart coverage for command-only, args-only, both, omission, and
  independent settings across multiple application/init containers, including
  whitespace, empty arguments, repeated flags, and literal expressions.
- Validation: 207 unittest tests passed, including Basic/Medium equivalence;
  Helm lint passed. No CLI or full Advanced equivalence changes.
- Advanced remains blocked by serviceAccount, explicit service.container, and
  Service targeting without a declared container port.

## 2026.09.15.15 - [0.2.0]

- Added init[] translation to ordered Helm initContainers values and a separate
  Deployment initContainers block, omitted when no init containers are declared.
- Reused container translation for images/policies, environment/resource references,
  requests/limits, and mounts. Init containers allocate shared volumes before application
  containers, matching KubernetesRenderer; resource declarations remain unduplicated.
- Added one/multiple-init tests for ordering, independent settings, shared resources,
  volume deduplication, absence, and continued command/args rejection.
- Validation: 206 unittest tests passed, including Basic/Medium equivalence; Helm lint passed.
- Advanced remains blocked by serviceAccount, command/args, explicit service.container,
  and Service targeting without a declared port. No full Advanced equivalence or CLI changes.

## 2026.09.15.14 - [0.2.0]

- Added ordered multi-container Helm values and Deployment rendering. One shared
  translator preserves each container's image/policy, ports, environment, resource
  consumption, requests/limits, mounts, and probes. Single-container values remain compatible.
- Kept ConfigMaps, Secrets, and PVCs application-scoped; volumes are deduplicated
  across containers by resource kind/name in first-consumption order.
- Added independent-settings/shared-resource tests and retained Basic/Medium
  equivalence regressions. Validation: 203 unittest tests passed; Helm lint passed.
- Advanced remains blocked by init containers, serviceAccount, command/args,
  explicit service.container, and Service targeting without a declared port.
  No CLI selection or full Advanced equivalence was added.

## 2026.09.15.13 - [0.2.0]

- Added configuration/Secret file loading in HelmRenderer, resolving paths against
  the existing base_dir render context. UTF-8 key=value parsing, comments,
  whitespace, duplicate/key validation, and substitution match KubernetesRenderer.
- Preserved resource names, inline data behavior, chart values, and Application
  immutability. Helm consumes resolved data without accessing the original files.
- Added relative-path, substitution, missing/invalid file, immutability, and chart
  tests. Validation: 200 unittest tests passed; Helm lint passed.
- The unchanged Advanced example remains blocked by multiple/init containers,
  serviceAccount, command/args, explicit service container selection, and a Service
  without a declared container port. No full Advanced equivalence was performed.

## 2026.09.15.12 - [0.2.0]

- Completed rendering of the unchanged Medium example by adding literal env
  values/Deployment output, LoadBalancer support, and explicit Service targetPort
  translation. Existing schema, KubernetesRenderer, and CLI remain unchanged.
- Added actual Medium end-to-end and semantic equivalence coverage across all
  five resources, including identity/selectors, container settings, resource data,
  environment ordering, PVCs, mounts, probes, Service routing, and service accounts.
- Comparisons ignore only descriptive Helm resource labels, normalize the default
  service account and Secret data encoding, and retain runtime-relevant ordering.
  Advanced features and file-based configuration/Secrets remain unsupported.
- Validation: 197 unittest tests passed; Helm lint passed; Medium helm template
  exited successfully and produced Secret, ConfigMap, PVC, Service, and Deployment YAML.

## 2026.09.15.11 - [0.2.0]

- Added Helm HTTP readiness, liveness, and startup probe values and conditional
  Deployment rendering, preserving path, numeric/named ports, and timing fields.
- Mapped ready/live aliases and frequencySeconds to Kubernetes probe names and
  periodSeconds. Omitted timing fields retain Application defaults; undeclared
  probes remain absent, matching KubernetesRenderer semantics.
- Added individual/all-probe tests for values, explicit/default timings, ports,
  immutability, and chart output. Existing renderer regressions remain covered.
- Validation: 194 unittest tests passed; Helm lint passed. Schema,
  KubernetesRenderer, and CLI are unchanged; file inputs remain unsupported.

## 2026.09.15.10 - [0.2.0]

- Added Helm volumes and volumeMounts for configuration, Secrets, and storage;
  the Deployment template renders them only when mounts are declared.
- Preserved Application-defined resource references, `<application>-<storage>`
  PVC names, mount paths and order, read-only ConfigMap/Secret mounts, and default
  read-write PVC mounts. Repeated sources share volumes without cross-kind collisions.
- Added focused values and chart mount tests, including KubernetesRenderer mount
  semantics and resource references. Basic, ConfigMap, Secret, and PVC regressions pass.
- File-based configuration/Secrets, probes, and other unsupported capabilities
  remain deferred. The Application schema, KubernetesRenderer, and CLI are unchanged.
- Validation: 191 unittest tests passed; Helm lint passed.

## 2026.09.15.9 - [0.2.0]

- Added Helm storage values and a PVC template preserving storage name, size,
  optional storageClass, and accessModes. Claims use `<application>-<storage>`
  names and match KubernetesRenderer PVC semantics; absent storage emits no PVC.
- Added tests for values/defaults, claim identity and spec, omitted storage class,
  absent PVCs, and continued rejection of storage mounts. Basic, ConfigMap, and
  Secret behavior remains covered by existing regressions.
- Mounts, probes, file-based configuration/Secrets, and other unsupported
  capabilities remain deferred; the schema, KubernetesRenderer, and CLI are unchanged.
- Validation: 190 unittest tests passed; Helm lint passed.

## 2026.09.15.8 - [0.2.0]

- Added inline Secret values and a Secret chart template using Application-defined
  names, type Opaque, and stringData with KubernetesRenderer's inline data semantics.
- Added ordered secretRef environment consumption after configuration references,
  preserving declaration and consumption order and environment substitution.
- Shared inline data translation between configuration and Secrets. File-based
  Secrets, storage, mounts, probes, and other unsupported capabilities still fail.
- Added values and chart tests for multiple/unconsumed Secrets, string data,
  substitution errors, ordering, and combined ConfigMap/Secret consumption.
  Existing Basic and ConfigMap regressions remain covered.
- Validation: 187 unittest tests passed; Helm lint passed.

## 2026.09.15.7 - [0.2.0]

- Added inline configuration values, ConfigMap templates, and ordered environment
  consumption through `configMapRef`, using Application-defined names.
- Preserved string conversion and environment-variable substitution. Configuration
  files, Secrets, storage, mounts, probes, and other unsupported capabilities still
  fail explicitly.
- Added tests for configuration translation, multiple/unconsumed ConfigMaps,
  empty and multiline data, reference ordering, and unsupported capabilities.
- Validation: 184 unittest tests passed; Helm lint passed.

## 2026.09.15.6 - [0.2.0]

- Added equivalence tests for resource kinds/names, labels/selectors, replicas,
  container settings, resource requests/limits, and Service routing.
- Fixed chart resource names and application labels to use the Application name;
  removed release-specific selector constraints and updated pod lookup instructions.
- Ignored only descriptive Helm resource labels and normalized omitted
  `serviceAccountName` to `default` in comparisons.
- Validation: 181 unittest tests passed; Helm lint passed.

## 2026.09.15.5 - [0.2.0]

- Added parser-to-values-to-Helm integration coverage for successful templating,
  YAML parsing, and exactly one Deployment and one Service.
- Removed the connection-test hook that emitted an unexpected Pod.
- Validation: 180 unittest tests passed; Helm lint and Basic `helm template` passed.

## 2026.09.15.4 - [0.2.0]

- Updated chart defaults and templates to consume `replicaCount`, `containerName`,
  image/pull policy, declared ports, resources, and Service type/port/targetPort.
- Removed legacy scaling defaults and Service-port-derived container ports.
  Service resources, connection hooks, and notes now honor `service.enabled`;
  service account creation remains controlled by `serviceAccount.create`.
- Added focused chart tests for Basic values and optional Service/ports and
  service account creation.
- Validation: 179 unittest tests passed; Helm lint passed.

## 2026.09.15.3 - [0.2.0]

- Extended `HelmRenderer` from the skeleton to generate Basic values, replacing
  `Renderer[Never]` with `Renderer[dict[str, Any]]`. Supported intent includes
  static replicas, container identity, image/pull policy, ports, resources, and
  ClusterIP Service targeting. Unsupported capabilities fail explicitly.
- Moved image-reference splitting into the Helm renderer module; the legacy
  generator reuses it while preserving its existing output.
- Added values, image-reference, optional-resource, immutability, and rejection
  tests. Chart alignment and CLI renderer selection remained deferred.
- Validation: 177 unittest tests passed.

## 2026.09.15.2 - [0.2.0]

- Added an isolated `HelmRenderer` skeleton implementing `Renderer[Never]` and
  accepting the existing validated `Application` model.
- Rendering intentionally raised `NotImplementedError` with the message
  "Helm rendering is not implemented yet." No values or templates were generated.
- Preserved the Application schema, KubernetesRenderer behavior, CLI renderer
  selection, and legacy Helm generator.
- Added a focused test for renderer contract inputs, intentional failure, and
  Application immutability.
- Validation: 174 unittest tests passed.

## 2026.09.15.1 - [0.2.0]

- Added the renderer-independent `Renderer[Output]` contract and Kubernetes
  adapter; routed the CLI through the adapter.
- Preserved the Application schema, Kubernetes behavior, and existing manifest
  APIs. Added boundary tests for output parity, file resolution, immutability,
  and legacy compatibility, and updated architecture/source/test guides.
- Validation: 173 unittest tests passed.

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
