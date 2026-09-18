"""Build the Linux artifact with the current interpreter (use an isolated venv)."""

import argparse
import ast
import hashlib
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def release_version(tag: str = "") -> str:
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    module = ast.parse((ROOT / "src/kubeapp/__init__.py").read_text())
    code_version = next(ast.literal_eval(node.value) for node in module.body
                        if isinstance(node, ast.Assign)
                        and any(isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets))
    if not re.fullmatch(r"\d+\.\d+\.\d+", version) or code_version != version:
        raise ValueError("Package and runtime release versions must match MAJOR.MINOR.PATCH")
    if tag and tag != f"v{version}":
        raise ValueError("Release tag must exactly match the package version")
    return version


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default="", help="Require a matching release tag before building")
    args = parser.parse_args()
    if sys.platform != "linux" or platform.machine() != "x86_64":
        parser.error("Build natively on Linux x86_64; cross-compilation is not supported")
    version = release_version(args.tag)
    name = f"kube-app-{version}-linux-x86_64"
    subprocess.run([
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--noupx",
        "--name", name, "--paths", str(ROOT / "src"),
        "--specpath", str(ROOT / "build/spec"), "--workpath", str(ROOT / "build/pyinstaller"),
        "--distpath", str(ROOT / "dist"),
        "--exclude-module", "pip", "--exclude-module", "setuptools",
        "--exclude-module", "pytest", "--exclude-module", "unittest",
        str(ROOT / "src/kubeapp/__main__.py"),
    ], cwd=ROOT, env={**os.environ, "PYTHONHASHSEED": "0"}, check=True)
    artifact = ROOT / "dist" / name
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    artifact.with_name(name + ".sha256").write_text(f"{digest}  {name}\n", encoding="ascii")
    print(f"Built {artifact}")


if __name__ == "__main__":
    main()
