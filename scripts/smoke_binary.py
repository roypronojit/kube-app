"""Test a copied packaged ELF executable; no repository inputs are mounted/used.

The Python test driver runs outside the tested process/container. --container-image
also proves that the runtime image contains no Python, pip, virtualenv or Helm.
"""

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

import yaml


def smoke(binary: Path, container_image: str | None = None) -> None:
    binary = binary.resolve(strict=True)
    if binary.read_bytes()[:4] != b"\x7fELF":
        raise ValueError("Expected a packaged Linux ELF executable, not a script")
    checksum = binary.with_name(binary.name + ".sha256").read_text(encoding="ascii").split()
    assert checksum == [hashlib.sha256(binary.read_bytes()).hexdigest(), binary.name], "Checksum mismatch"
    with tempfile.TemporaryDirectory(prefix="kube-app-smoke-") as directory:
        root = Path(directory)
        executable = root / "kube-app"
        shutil.copyfile(binary, executable)
        executable.chmod(0o755)
        (root / "run").mkdir()
        (root / "inputs").mkdir()
        (root / "chart/templates").mkdir(parents=True)
        (root / "chart/Chart.yaml").write_text("apiVersion: v2\nname: external\nversion: 1.0.0\n")
        (root / "chart/templates/anything.yaml").write_text("kind: Deployment\n---\nkind: Secret\n---\nkind: ConfigMap\n")
        application = {
            "name": "smoke", "replicas": 2,
            "containers": [{"name": "web", "image": "nginx:1.27"}],
            "configuration": [{"name": "config", "file": "settings.env"}],
            "secrets": [{"name": "credentials", "file": "secrets.env"}],
        }
        source = root / "inputs/app.yaml"
        source.write_text(yaml.safe_dump(application))
        (root / "inputs/settings.env").write_text("MODE=demo\n")
        (root / "inputs/secrets.env").write_text("TOKEN=${SMOKE_SECRET}\n")
        (root / "inputs/invalid.yaml").write_text("name: invalid\ncontainers: []\n")
        before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
        env = {"PATH": "/no-tools", "HOME": "/nonexistent", "LANG": "C.UTF-8",
               "PYTHONHOME": "/no-python", "PYTHONPATH": "/no-python",
               "VIRTUAL_ENV": "/no-venv", "SMOKE_SECRET": "smoke-placeholder-token"}
        if container_image:
            subprocess.run(["docker", "run", "--rm", "--network", "none", container_image,
                            "/bin/sh", "-c", "! command -v python && ! command -v python3 && "
                            "! command -v pip && ! command -v pip3 && ! command -v helm"], check=True)

        def invoke(*args, expected=0, secret=True):
            runtime_env = dict(env)
            if not secret:
                runtime_env.pop("SMOKE_SECRET")
            if container_image:
                command = ["docker", "run", "--rm", "--network", "none",
                           "--user", f"{os.getuid()}:{os.getgid()}",
                           "--mount", f"type=bind,src={root},dst=/work", "--workdir", "/work/run"]
                for key, value in runtime_env.items():
                    command += ["--env", f"{key}={value}"]
                command += [container_image, "/work/kube-app", *args]
                result = subprocess.run(command, capture_output=True, text=True, timeout=60)
            else:
                result = subprocess.run([str(executable), *args], cwd=root / "run", env=runtime_env,
                                        capture_output=True, text=True, timeout=30)
            assert "smoke-placeholder-token" not in result.stderr, "Secret leaked to stderr"
            assert result.returncode == expected, (
                f"Unexpected exit code {result.returncode} for {args}\nstderr:\n{result.stderr}"
            )
            if expected:
                assert not result.stdout and result.stderr, "Failure stream contract violated"
            return result

        for args in (("--help",), ("-h",), ("render", "--help"), ("render", "-h")):
            result = invoke(*args)
            assert "usage:" in result.stdout and not result.stderr
        assert "valid" in invoke("validate", "../inputs/app.yaml").stdout
        invoke("validate", "../inputs/invalid.yaml", expected=1)
        for fmt in (None, "kubernetes", "k8s", "k", "helm", "h"):
            args = ["render", "../inputs/app.yaml"]
            helm = fmt in ("helm", "h")
            if fmt:
                args += ["-f", fmt]
            if helm:
                args += ["-c", "../chart"]
            result = invoke(*args, "--name", "renamed")
            if helm:
                values = yaml.safe_load(result.stdout)
                assert isinstance(values, dict) and "kind" not in values
                assert values["name"] == "renamed" and values["replicaCount"] == 2
                assert values["configuration"][0]["data"] == {"MODE": "demo"}
                assert values["secrets"][0]["data"]["TOKEN"] == env["SMOKE_SECRET"]
                assert "NOTE:" in result.stderr
            else:
                docs = list(yaml.safe_load_all(result.stdout))
                assert not result.stderr
                assert next(doc for doc in docs if doc["kind"] == "Deployment")["metadata"]["name"] == "renamed"
                assert next(doc for doc in docs if doc["kind"] == "Secret")["stringData"]["TOKEN"] == env["SMOKE_SECRET"]
            for flag in ("-o", "--output"):
                written = invoke(*args, "-n", "renamed", flag, "nested/output.yaml")
                assert not written.stdout and written.stderr == result.stderr
                assert (root / "run/nested/output.yaml").read_text() == result.stdout

        helm_args = ["render", "../inputs/app.yaml", "-f", "helm"]
        supported = yaml.safe_load(invoke(*helm_args, "--chart", "../chart").stdout)
        (root / "chart/values.yaml").write_text(yaml.safe_dump(supported))
        assert not invoke(*helm_args, "-c", "../chart").stderr
        (root / "chart/values.yaml").write_text("{}\n")
        warning = invoke(*helm_args, "-c", "../chart")
        assert "WARNING:" in warning.stderr and yaml.safe_load(warning.stdout) == supported
        destination = root / "run/existing.yaml"
        destination.write_text("existing\n")
        for args, code in ((helm_args, 2), (helm_args + ["-c", "../absent"], 1),
                           (["render", "../inputs/app.yaml", "-f", "invalid"], 2),
                           (["render", "../inputs/invalid.yaml"], 1),
                           (helm_args + ["-c", "../inputs/app.yaml"], 1),
                           (helm_args + ["-c", "../inputs"], 1)):
            invoke(*args, "-o", "existing.yaml", expected=code)
            assert destination.read_text() == "existing\n"
        invoke(*helm_args, "-c", "../chart", "-o", "existing.yaml", secret=False, expected=1)
        assert destination.read_text() == "existing\n"
        # Only our fixture edits changed the external chart; runtime edits are forbidden.
        for path, content in before.items():
            assert path.read_bytes() == content, "Runtime modified an external input"
    print("Packaged executable smoke tests PASS" + (f" ({container_image}, no host Python)" if container_image else " (isolated PATH/cwd)"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument("--container-image", help="Also isolate runtime in a minimal Linux Docker image")
    args = parser.parse_args()
    smoke(args.binary, args.container_image)
