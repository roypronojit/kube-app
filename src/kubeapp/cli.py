import argparse
import subprocess
import sys
from pathlib import Path

import yaml

from kubeapp.renderers import HelmRenderer, KubernetesRenderer
from kubeapp.parser import ApplicationParseError, load_application


def _renderer_name(value: str) -> str:
    aliases = {"kubernetes": "kubernetes", "k8s": "kubernetes", "k": "kubernetes",
               "helm": "helm", "h": "helm"}
    try:
        return aliases[value]
    except KeyError:
        raise argparse.ArgumentTypeError(
            "renderer must be kubernetes (k8s, k) or helm (h)"
        ) from None


def _render_helm(application, base_dir: Path) -> str:
    values = HelmRenderer().render(application, base_dir)
    chart = Path(__file__).resolve().parents[2] / "charts/kube-app"
    result = subprocess.run(
        ["helm", "template", "kube-app", str(chart), "-f", "-"],
        input=yaml.safe_dump(values, sort_keys=False),
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode:
        raise ValueError(result.stderr.strip() or "helm template failed")
    return result.stdout


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kube-app",
        description="Developer-facing Kubernetes application platform",
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate an application definition",
    )

    validate_parser.add_argument(
        "file",
        help="Path to the application YAML file",
    )

    render_parser = subparsers.add_parser(
        "render",
        help="Generate Kubernetes manifests from an application definition",
    )

    render_parser.add_argument(
        "file",
        help="Path to the application YAML file",
    )

    render_parser.add_argument("-o", "--output", help="Write manifests to this file")
    render_parser.add_argument(
        "-r", "--renderer", type=_renderer_name, default="kubernetes",
        metavar="RENDERER", help="Renderer: kubernetes (k8s, k; default) or helm (h)",
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command in {"validate", "render"}:
        try:
            application = load_application(args.file)

        except ApplicationParseError as exc:
            print(f"Validation failed:\n{exc}", file=sys.stderr)
            return 1

        if args.command == "validate":
            print(f"Application '{application.name}' is valid.")
            return 0

        try:
            base_dir = Path(args.file).resolve().parent
            if args.renderer == "helm":
                rendered = _render_helm(application, base_dir)
            else:
                manifests = KubernetesRenderer().render(application, base_dir)
                rendered = yaml.safe_dump_all(manifests, sort_keys=False)
            if args.output:
                output = Path(args.output)
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(rendered, encoding="utf-8")
            else:
                print(rendered, end="")

        except (ValueError, OSError, NotImplementedError, subprocess.SubprocessError) as exc:
            print(f"Render failed:\n{exc}", file=sys.stderr)
            return 1

        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
