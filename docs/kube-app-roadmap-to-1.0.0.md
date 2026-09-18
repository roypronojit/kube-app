# kube-app Roadmap to 1.0.0

> From architecture milestone to a Linux-first, CI/CD-first product.

**Baseline:** v0.2.0 release: September 18, 2026.\
**Target:** v1.0.0 target release: November 2, 2026, subject to quality gates.

## 1. Product direction

kube-app is currently primarily a portfolio-quality Platform Engineering
project and a source of credible technical material for GitHub,
LinkedIn, and career discussions.

The goal is **not** to maximize Kubernetes feature count. The goal is to
demonstrate application/platform abstraction, developer experience,
Kubernetes and Helm integration, CI/CD engineering, artifact
engineering, Linux distribution, release automation, and product
lifecycle thinking.

**v0.2.0 establishes the application architecture.** The journey from
**v0.3.x to v1.0.0 is primarily productization**: turning the tested
Python application into a repeatably built, tested, packaged, and
distributable Linux CLI. The v0.3.x versions are development checkpoints
for one distribution milestone and are released together after v0.3.2.

## 2. Architectural baseline at v0.2.0

kube-app uses one renderer-independent **Application Model** with
deployment-native outputs.

``` text
app.yaml
   |
   v
Parse / Validate
   |
   v
Application Model
   |
   +-- Kubernetes --> Kubernetes manifests
   |
   +-- Helm + external chart --> values.yaml
```

Kubernetes format produces final manifests:

``` bash
kube-app render app.yaml -f k
```

Helm format inspects an externally supplied chart and produces values
YAML:

``` bash
kube-app render app.yaml -f h -c ./existing-chart
```

kube-app does **not** invoke `helm template` in this path. The external
chart remains owned by the application/platform team.

### v0.2.0 QA principle

Fix genuine correctness issues, cross-layer consistency gaps, misleading
diagnostics, and meaningful quality defects in functionality kube-app
already claims to support. Do not delay v0.2.0 merely to expose
additional Kubernetes functionality.

## 3. v1.0.0 product boundary

The standalone application artifact will contain:

``` text
kube-app executable
├── Python runtime/interpreter
├── src/kubeapp application code
└── required runtime Python dependencies
```

Users should not need a separately installed Python, pip, virtualenv, or
`pip install kube-app`.

Runtime inputs remain external: `app.yaml`, referenced
configuration/secret files, and the external Helm chart for Helm output.

The executable and official image should **not** embed Helm, kubectl,
the reference chart, examples, tests, docs, or the source repository.

As far as practical, the same tested standalone artifact should feed
every distribution format:

``` text
                   standalone kube-app artifact
                              |
             +----------------+----------------+
             |                |                |
             v                v                v
        OCI image            DEB              RPM
```

Avoid separate execution implementations such as a standalone executable
in RPM while the container uses `pip install`.

## 4. Release roadmap

| Version | Primary milestone | Acceptance outcome | Target date |
| --- | --- | --- | --- |
| **v0.2.0** | Architecture & QA | Stable Kubernetes-manifest and Helm-values architecture; claimed capabilities consistent and tested | **Sep 18, 2026 — released** |
| **v0.3.0** | Standalone Linux executable + release foundation | Runs without host Python/pip/venv; PR CI and tag-driven release automation established | **Sep 18, 2026 — pushed** |
| **v0.3.1** | OCI / CI-CD image | Versioned image works directly in pipeline/workspace scenarios and extends the same release pipeline | **Sep 25, 2026** |
| **v0.3.2** | DEB + RPM | Native Linux installation into PATH; binary, OCI, DEB and RPM distribution paths complete | **Oct 2, 2026** |
| **v0.3.x release** | Complete Linux distribution milestone | Release the completed 0.3 series together after integrated validation of binary, OCI, DEB and RPM | **Oct 2, 2026** |
| **Hardening** | Integrated release hardening | Clean-environment, consistency, security, metadata, checksum and cross-artifact validation | **Oct 3–18, 2026** |
| **v1.0.0-rc.1** | Product RC | Complete product consumed like an external user; release-blocking fixes only | **Oct 19, 2026** |
| **v1.0.0** | First product deliverable | Linux-first, CI/CD-first product with repeatable automated releases | **Nov 2, 2026** |

Versions are **quality gates, not calendar gates**. The v0.3.0, v0.3.1 and
v0.3.2 checkpoints belong to one productization series; they are not
separate public release events. The completed v0.3 series is released
together after v0.3.2 passes integrated validation.

## 5. v0.3.0 --- Standalone Linux executable + release foundation

### Objective

Establish the distributable Linux artifact and the release pipeline that
the rest of the v0.3 series extends.

### Status

**Implementation complete and branch pushed.** Local validation passed with
267 unit tests, packaged-binary smoke tests, workflow linting, and
`git diff --check`. Hosted GitHub execution remains part of integrated
v0.3 validation.

### Scope

-   Build Linux x86_64 standalone `kube-app` with PyInstaller one-file mode.
-   Bundle the required Python runtime and runtime dependencies.
-   Keep application files, referenced files, and external Helm charts external.
-   Build on Ubuntu 22.04 for a defined Linux/glibc baseline.
-   Add PR/branch CI for tests, build, and packaged-binary smoke checks.
-   Add tag-driven release automation.
-   Generate and verify SHA256 checksums.
-   Ensure publication uses the same executable that passed smoke tests.

### Acceptance

``` bash
./kube-app --help
./kube-app validate app.yaml
./kube-app render app.yaml -f k
./kube-app render app.yaml -f h -c ./chart
./kube-app render app.yaml -f k -o manifests.yaml
```

Also verify environment substitution, referenced files, chart inspection,
stdout/stderr separation, diagnostics, exit codes, output-file behavior,
and execution without relying on host Python, pip, a virtualenv, or Helm.

### Release foundation

``` text
source revision
    |
    v
tests
    |
    v
build standalone executable
    |
    v
smoke test packaged executable
    |
    v
SHA256 checksum
    |
    v
release artifact
```

v0.3.1 and v0.3.2 extend this same pipeline rather than creating separate
application implementations.

## 6. v0.3.1 --- OCI image for CI/CD-first consumption

### Objective

Make the established standalone artifact directly consumable by CI/CD
pipelines through a versioned OCI image.

Conceptually:

``` yaml
image: <registry>/kube-app:0.3.1

script:
  - kube-app validate app.yaml
  - kube-app render app.yaml -f k -o manifests.yaml
```

The image should contain minimal Linux userspace, the established
standalone executable, and required runtime necessities/certificates.

Test mounted workspaces, relative paths, referenced files, environment
variables, external charts, generated artifacts, stdout/stderr,
exit-code propagation, non-root execution where practical, and
CI-friendly invocation behavior.

Extend the existing release workflow to build, test, version, and publish
the OCI artifact.

## 7. v0.3.2 --- Native Linux packages

### Objective

Complete the v0.3 distribution milestone with native Linux installation
while continuing to distribute the same established application artifact.

-   **DEB:** Debian / Ubuntu
-   **RPM:** RHEL / Fedora / Rocky / Alma and rpm/dnf/yum ecosystems

There is no need for separate yum and dnf application builds; both consume
RPM packages.

### Scope

-   Produce versioned `.deb` and `.rpm` packages.
-   Package the established standalone executable.
-   Install `kube-app` into a standard executable path.
-   Test fresh install, upgrade, uninstall, permissions, and version metadata.
-   Extend automation to build, test, checksum, and publish both package formats.
-   Validate binary, OCI, DEB, and RPM outputs together before the v0.3 series release.

Initially, local package-file installation is sufficient. Hosted APT/RPM
repositories can be evaluated separately.

## 8. Integrated release hardening and v1.0.0 release candidate

Release hardening is not a separate minor release. It is built into the
acceptance criteria for v0.3.0, v0.3.1, and v0.3.2, then validated across
all distribution paths before the release candidate.

By the RC, hardening must cover:

-   one source revision/version driving all artifacts
-   consistent version metadata
-   SHA256 checksums
-   clean-environment and representative Linux-family testing
-   executable/package permissions and host-library assumptions
-   relative path, signal, and exit-code behavior
-   container user/security posture
-   deterministic artifact naming and release failure handling
-   repeatable/reproducible release behavior where practical

A failed required gate should stop publication rather than create a
partially trusted release.

### v1.0.0-rc.1

`v1.0.0-rc.1` is where kube-app is consumed like an external user would
consume it.

The RC must be generated entirely by the release pipeline. Focus on
regression testing, clean installation/use, CI image usage, package
behavior, documentation accuracy, and release-blocking bugs.

Avoid feature expansion during RC. Create `rc.2` only if fixes justify
another candidate.

## 9. v1.0.0 --- First product deliverable

v1.0.0 does **not** need another headline feature. It promotes
productization already proven through lower releases.

``` text
src/kubeapp
     |
     v
automated tests/build
     |
     v
standalone Linux kube-app artifact
     |
     +----------------+----------------+
     |                |                |
     v                v                v
Linux binary       OCI image        packages
                                    /                                        DEB      RPM
     |                |              |
     +----------------+--------------+
                      |
                      v
             automated smoke tests
                      |
                      v
                 checksums
                      |
                      v
              published release
```

## 10. CI/CD and release model

``` text
feature / fix
     |
     v
Pull Request
     |
     v
CI quality gates
     |
     v
main
     |
     v
version tag
     |
     v
Release workflow
     |
     v
tested standalone artifact
     |
     +-------------+-------------+
     |             |             |
     v             v             v
binary         OCI image      DEB / RPM
     |             |             |
     +-------------+-------------+
                   |
                   v
              smoke tests
                   |
                   v
               checksums
                   |
                   v
             publication
```

Release automation begins in **v0.3.0** and is extended through **v0.3.1** and **v0.3.2** before the v0.3 series is released.

## 11. Post-1.0 release experience

Future patches and enhancements should require engineering work on the
product, not repeated manual packaging work.

``` text
bug fix
   |
   v
PR + CI
   |
   v
merge
   |
   v
v1.0.1 tag
   |
   v
release automation
   |
   +-- standalone binary
   +-- OCI image
   +-- DEB
   +-- RPM
   +-- SHA256SUMS
   |
   v
v1.0.1 release
```

The same model applies to future minor and major releases.

## 12. Scope discipline

From v0.2.0 to v1.0.0:

1.  Productization is the primary goal, not broad Kubernetes feature
    expansion.
2.  Fix genuine bugs and inconsistencies found during packaging/testing.
3.  Do not add functionality merely because Kubernetes supports it.
4.  Do not bundle Helm or kubectl without a demonstrated architectural
    requirement.
5.  Do not embed the reference chart into the public runtime path.
6.  Do not create separate application implementations for binary, OCI,
    DEB, and RPM.
7.  Keep the Application Model renderer/output-independent.
8.  Keep external Helm chart ownership with the application/platform
    team.
9.  Preserve clean stdout for generated YAML and stderr for diagnostics.
10. Preserve current CLI and exit-code semantics unless a genuine
    product issue requires change.

### Initial 1.0 targets

**In scope:** Linux x86_64 executable, OCI image, DEB, RPM.

**Not required:** Windows, macOS, Homebrew, Chocolatey, Winget, bundled
Helm, bundled kubectl, broad Kubernetes feature expansion.

Linux ARM64 can be added later when justified.

## 13. Platform Engineering story

Python is the implementation language; it is not the main story.

``` text
Application abstraction
        |
Developer experience
        |
Validation and diagnostics
        |
Kubernetes
        |
Helm contracts
        |
Automated testing
        |
Artifact engineering
        |
OCI / containers
        |
Linux packaging
        |
CI/CD
        |
Release automation
        |
Security / supply-chain awareness
        |
Operational lifecycle
```

The repository and public material should describe the **current
architecture and its rationale**. It does not need to narrate every
intermediate implementation.

## 14. Definition of done for v1.0.0

-   [ ] Standalone Linux executable works without host Python, pip, or
    virtualenv.
-   [ ] Required Python runtime and runtime dependencies are bundled.
-   [ ] The same tested application artifact underpins supported
    distribution formats as far as practical.
-   [ ] Versioned OCI image supports CI/CD workspace use.
-   [ ] DEB installs a working `kube-app`.
-   [ ] RPM installs a working `kube-app`.
-   [ ] Install/upgrade/uninstall behavior is validated.
-   [ ] PR CI validates changes without publishing.
-   [ ] Version tags trigger release automation.
-   [ ] Release automation builds and tests all supported artifacts.
-   [ ] Release automation generates checksums.
-   [ ] Release automation publishes artifacts consistently.
-   [ ] Clean-environment regression tests cover important
    CLI/file/chart paths.
-   [ ] Version metadata is consistent across artifacts.
-   [ ] Documentation covers installation and CI usage.
-   [ ] Documentation covers runtime inputs and architecture boundaries.
-   [ ] Known limitations are accurate.
-   [ ] v1.0.0 uses the same automated process intended for v1.0.1 and
    later.

## 15. Working schedule

``` text
Sep 18, 2026     v0.2.0  Architecture & QA — released
                     |
Sep 18, 2026     v0.3.0  Standalone executable + release foundation — pushed
                     |
Sep 25, 2026     v0.3.1  OCI image
                     |
Oct 2, 2026      v0.3.2  DEB + RPM
                     |
Oct 2, 2026              Release completed v0.3 series together
                     |
Oct 3–18, 2026            Integrated release hardening
                     |
Oct 19, 2026     v1.0.0-rc.1
                     |
Nov 2, 2026      v1.0.0
```

**Working target:** November 2, 2026. The v0.3.x checkpoints form one
Linux-distribution milestone and are released together after v0.3.2;
they are not separate public release events. Dates remain quality-gate
targets rather than forced deadlines.

## Guiding principle

> **v0.2.0 proves the architecture. The v0.3.x series turns it into a
> distributable Linux product through a standalone executable, OCI image,
> native packages, and one automated release lifecycle. The completed
> v0.3 series is released together; the RC then validates the whole product,
> and v1.0.0 establishes the stable delivery baseline.**
