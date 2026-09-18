# Standalone Linux distribution (v0.3.0)

The Linux x86_64 executable bundles kube-app, CPython and required runtime Python
dependencies using PyInstaller one-file mode. Users do not need Python, pip, a
virtualenv, Helm or a Kubernetes cluster for generation. Inputs remain external:
app.yaml, referenced configuration/secret files and the chart passed with --chart.
No chart, examples, tests, docs, Helm or kubectl are packaged.

## Install a released binary

After the v0.3.0 tag workflow has published the release:

```sh
version=0.3.0
artifact="kube-app-${version}-linux-x86_64"
base="https://github.com/roypronojit/kube-app/releases/download/v${version}"
curl -fLO "$base/$artifact"
curl -fLO "$base/$artifact.sha256"
sha256sum --check "$artifact.sha256" &&
  install -Dm755 "$artifact" "$HOME/.local/bin/kube-app"
export PATH="$HOME/.local/bin:$PATH"
kube-app --help
kube-app validate app.yaml
kube-app render app.yaml -f k -o manifests.yaml
kube-app render app.yaml -f h -c ./existing-chart -n preview -o values.yaml
```

Download both files from the same trusted release. The SHA256 checksum detects
corruption; it is not a signature. Diagnostics remain on stderr, YAML goes to
stdout or --output, and existing CLI exit codes and secret handling are unchanged.
The executable may be renamed to kube-app; checksum verification uses its original name.

## Platform scope and runtime requirements

Official builds use Ubuntu 22.04 x86_64 and Python 3.11.16. The supported baseline
is glibc-based Linux x86_64 with glibc 2.35 or newer, the standard dynamic loader,
C runtime libraries and zlib (libz.so.1). This is not a statically linked binary. Alpine/musl,
older glibc, ARM64, native Windows and macOS are not supported by this artifact.
Use WSL on Windows for a compatible Linux environment.

One-file mode extracts its bundled libraries into a temporary directory at startup.
It needs writable temporary storage that permits loading executable/shared-library
content; on systems with /tmp mounted noexec, set TMPDIR to a suitable private
directory. App/chart file access uses the caller's permissions. Do not install the
binary setuid. No runtime downloads or network access are needed.

PyInstaller does not bundle glibc; building on a newer system can raise the minimum
runtime requirement. See [PyInstaller's Linux compatibility guidance](https://pyinstaller.org/en/stable/usage.html#making-gnu-linux-apps-forward-compatible).
Local builds must be tested on their intended deployment baseline; a local build
is not automatically identical to an official CI build.

## Local build and verification

Build natively on Linux x86_64 with Python 3.11, venv/pip support and binutils
(including objdump). Use a clean build environment to avoid unrelated packages:

```sh
python3.11 -m venv .tools/package-venv
.tools/package-venv/bin/python -m pip install -r packaging/requirements-build.txt
.tools/package-venv/bin/python -m pip install --no-deps --no-build-isolation -e .
.tools/package-venv/bin/python -m unittest discover -s tests -v
.tools/package-venv/bin/python scripts/build_linux.py --tag v0.3.0
.tools/package-venv/bin/python scripts/smoke_binary.py dist/kube-app-0.3.0-linux-x86_64
git diff --check
```

The existing WSL .venv/bin/python can create the isolated packaging venv as well.
The --tag guard is optional locally and mandatory in the release workflow; it
rejects tags that do not exactly match package/runtime versions. Build output:

* dist/kube-app-0.3.0-linux-x86_64
* dist/kube-app-0.3.0-linux-x86_64.sha256

Build/spec files and environments are ignored by Git. Dependency versions,
including PyInstaller hooks, are pinned in packaging/requirements-build.txt; update
them deliberately and rerun both gates. Stable filenames do not promise bit-for-bit
reproducible binaries across machines/toolchains.

The smoke driver uses Python/PyYAML only as test tooling. It copies the actual ELF
to a temporary directory, clears PATH and supplies invalid Python/venv locations.
It uses temporary external application/chart fixtures and exercises help, validation,
all format aliases, names, stdout/file outputs, relative files, substitution,
diagnostic isolation, non-fatal warnings, chart failures and output preservation.

For stronger isolation, test in a base image that contains no Python/pip/Helm:

```sh
docker pull ubuntu:22.04
.tools/package-venv/bin/python scripts/smoke_binary.py \
  dist/kube-app-0.3.0-linux-x86_64 --container-image ubuntu:22.04
```

Only the copied binary and temporary fixtures are mounted. The test driver stays
outside the container; runtime networking is disabled. CI requires this check.

## CI and releases

* ci.yml runs on PRs, branch pushes and manual dispatch. It calls build-linux.yml
  to install pinned dependencies, run the full unit suite, build/checksum, and run
  packaged smoke tests locally and in the Python-free Ubuntu container. Helm is
  installed solely for the internal reference-chart unit tests. CI uploads a
  short-lived Actions artifact and has no release publishing permission.
* release.yml runs only on v* tag pushes. The reusable build validates the exact
  vMAJOR.MINOR.PATCH tag against source versions before packaging. A mismatched tag
  fails without publishing. Publishing waits for all tests and smoke checks, then
  downloads the same tested artifact, verifies SHA256 and creates a GitHub Release
  with the executable and checksum. Only the publish job has contents: write.
* Release artifacts are not rebuilt in the publishing job. Existing releases are
  not silently overwritten; a repeated release creation requires manual review.
  No tag is created by CI, and normal branch/PR builds never publish a release.

Before tagging, review the diff/changelog and version consistency, run a green CI
build on GitHub, download and test that exact artifact on the supported target,
and confirm repository Actions/release-token permissions. Confirm both assets and
checksum after the tag workflow succeeds. This change does not itself create or
push a tag or publish a release. Signing, other architectures and additional
distribution formats remain outside v0.3.0.
