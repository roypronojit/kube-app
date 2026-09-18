# kube-app Developer Contract

**Baseline:** v0.2.0\
**Status:** Developer-facing behavioral contract

## 1. Purpose

This document defines the behavior application developers can rely on
when using `kube-app`.

The core contract is independent of distribution. Future distribution
formats may change how `kube-app` is installed or launched, but must
preserve the application behavior described here.

`kube-app` provides a small application-oriented specification and
translates that intent into deployment-native outputs.

``` text
app.yaml
   |
   v
parse / validate
   |
   v
Application model
   |
   +--------------------+
   |                    |
   v                    v
Kubernetes           Helm
manifests            values.yaml
```

## 2. Application specification

The developer supplies an `app.yaml` specification describing
application intent.

The specification is not intended to reproduce the complete Kubernetes
API. `kube-app` owns parsing, validation, and translation of the
capabilities represented by its application model.

The same application specification is used for both supported output
paths.

Referenced configuration and secret files remain external inputs. They
are read during rendering when required by those resources.

`${ENV_VAR}` substitution applies to configuration and secret data
during rendering. It is not general substitution across arbitrary
application-model fields.

`kube-app validate` validates the application model without reading
referenced configuration/secret files or resolving their environment
substitutions.

## 3. Validation contract

`kube-app validate` validates the application specification against the
supported application model and reports invalid input as a failure.

CLI overrides that affect the application model, including the
application-name override, must pass the same model validation rather
than bypassing it.

Validation of the application model is distinct from render-time
processing of referenced configuration/secret files and their
environment substitutions.

A validation failure must not be reported as successful output.

## 4. Kubernetes output contract

Kubernetes is the default output format.

Supported format names are:

``` text
kubernetes
k8s
k
```

For Kubernetes output, `kube-app` produces final Kubernetes manifest
YAML suitable for a direct Kubernetes workflow.

``` text
app.yaml
   |
   v
Application model
   |
   v
Kubernetes renderer
   |
   v
Kubernetes manifests
```

The Kubernetes path does not require an external Helm chart.

## 5. Helm output contract

Supported Helm format names are:

``` text
helm
h
```

For Helm output, `kube-app` generates Helm values YAML for an existing
chart supplied by the user or platform team.

``` text
app.yaml
   |
   v
Application model
   |
   + external chart
   |
   v
chart inspection / values mapping
   |
   v
values.yaml
```

The Helm path requires `--chart` / `-c`.

The supplied chart:

-   must exist;
-   must be a directory;
-   must contain `Chart.yaml`;
-   remains owned by the application/platform team; and
-   is not modified by `kube-app`.

Chart inspection is best-effort. `values.yaml` and `values.schema.json`,
when present, are used as declared values-contract information.

`kube-app` does not claim to understand arbitrary Helm template logic or
perform fuzzy remapping of arbitrary enterprise chart values.

Chart-mapping warnings and notes are non-fatal. They do not silently
filter generated values.

The public Helm output is values YAML. `kube-app` does not invoke
`helm template` as part of this output path.

## 6. CLI contract

The v0.2.0 public CLI includes:

| Option | Purpose |
| --- | --- |
| `-f`, `--format` | Select output format. Kubernetes is the default. |
| `-n`, `--name` | Override `Application.name`. |
| `-c`, `--chart` | Supply an external Helm chart for Helm output. |
| `-o`, `--output` | Write generated output to a file instead of stdout. |
| `-h`, `--help` | Display CLI help. |

`--chart` is required for Helm output and is rejected for Kubernetes
output.

The application-name override creates a validated application model with
the overridden application name. It does not mutate the original parsed
model.

Derived application resource names, labels, selectors, and generated PVC
references follow the application-name override. Explicitly supplied
names such as ConfigMap, Secret, container, init-container, and
service-account names remain explicit.

## 7. Output and diagnostics contract

When `--output` / `-o` is omitted, generated YAML is written to stdout.

When an output file is supplied, `kube-app` uses atomic replacement
semantics so that an existing output file is preserved if the new write
fails.

Diagnostics are written to stderr so that generated YAML on stdout or in
an output file remains clean.

For Helm chart mapping, unsupported/missing chart capabilities are
reported as warnings and mappings that cannot be determined reliably are
reported as notes. These diagnostics are non-fatal and do not silently
filter generated values.

This is distinct from an application input that the Helm translator
itself does not support. Such an unsupported input causes rendering to
fail with exit code `1`.

## 8. Exit-code contract

| Exit code | Meaning |
| --- | --- |
| `0` | Successful operation, including successful output with non-fatal chart-mapping warnings or notes. |
| `1` | Validation or rendering failure. |
| `2` | CLI usage error. |

Consumers, including CI/CD pipelines, may use these exit codes to
determine command success or failure.

## 9. File and path contract

`app.yaml`, referenced files, and external Helm charts are external
runtime inputs.

Path resolution follows these rules:

-   the CLI input path, external chart path, and output path are
    resolved relative to the process working directory when relative
    paths are supplied;
-   configuration and secret files referenced by `app.yaml` are resolved
    relative to the directory containing `app.yaml`.

Distribution mechanisms must preserve these path semantics.

## 10. Resource ownership boundary

Top-level resources describe what exists for the application. Container
and init-container fields describe how application components consume
those resources.

For storage, `kube-app` may generate a PersistentVolumeClaim from the
application specification. A configured storage class selects the
platform provisioner. `kube-app` does not create PersistentVolumes.

The supported Service types at this baseline are:

``` text
ClusterIP
NodePort
LoadBalancer
```

Support for `NodePort` refers to the Service type. The application
abstraction does not currently expose an explicit `nodePort` number.

## 11. Runtime dependency boundary

The developer contract does not require Helm for normal Kubernetes
generation or for Helm-values generation.

Helm may be used internally by the project for reference-chart
validation and testing, but it is not a runtime dependency of the public
Helm-values path.

The reference chart under `charts/kube-app/` is a reference and internal
test target. It is not an implicit chart used by the public Helm path.

`kubectl` is not part of the `kube-app` runtime contract.

## 12. Future distribution compatibility principle

At the v0.2.0 baseline, this section defines a compatibility principle
for future distribution mechanisms; it does not claim that OCI or native
Linux packages are available in v0.2.0.

Future distribution formats should preserve the same developer-visible
application behavior.

``` text
                    kube-app developer contract
                              |
              +---------------+---------------+
              |               |               |
              v               v               v
       standalone binary   OCI image      native package
              |               |               |
              +---------------+---------------+
                              |
                              v
                         same app.yaml
                         same validation
                         same outputs
                         same diagnostics
                         same exit semantics
```

A distribution mechanism may introduce installation- or
execution-specific requirements, but those requirements must be
documented separately and must not silently redefine the application
specification or renderer behavior.

## 13. Current limitations

The developer contract covers capabilities that `kube-app` explicitly
supports. It is not a promise to expose every Kubernetes or Helm
capability.

Current Helm translator limitations include:

-   digest-based image references are unsupported and cause rendering to
    fail with exit code `1`;
-   init-container ports are unsupported and cause rendering to fail
    with exit code `1`;
-   multiple or non-TCP ports are unsupported and cause rendering to
    fail with exit code `1`;
-   advanced Service networking is not represented by the current Helm
    translation contract;
-   explicit `nodePort` numbers are not represented by the current
    application model;
-   `ExternalName` and headless Services are not part of the current
    abstraction.

These unsupported application inputs are different from chart-mapping
warnings or notes. Chart-mapping diagnostics are non-fatal; unsupported
translator inputs that prevent rendering fail with exit code `1`.

Chart inspection remains best-effort. Unknown chart semantics may
therefore produce diagnostics rather than inferred mappings.

When an application requires behavior outside the `kube-app` abstraction,
developers can author Kubernetes manifests directly. Selecting
`-f kubernetes` still uses the `kube-app` application model and does not
bypass its limitations.

## 14. Compatibility principle

Changes to installation or distribution should not silently change this
contract.

Changes that intentionally alter application specification semantics,
validation behavior, generated-output semantics, CLI behavior,
diagnostics, path resolution, or exit codes should be treated as
developer-contract changes and documented accordingly.

> **Application specifications express application intent. Distribution
> mechanisms deliver kube-app. The distribution mechanism must not
> redefine the application contract.**
