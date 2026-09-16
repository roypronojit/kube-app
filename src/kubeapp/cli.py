import argparse
import sys
from pathlib import Path

import yaml
from pydantic import ValidationError

from kubeapp.models import Application
from kubeapp.chart_inspection import inspect_chart
from kubeapp.renderers import HelmRenderer, KubernetesRenderer
from kubeapp.parser import ApplicationParseError, load_application


def _format_name(value: str) -> str:
    aliases = {"kubernetes": "kubernetes", "k8s": "kubernetes", "k": "kubernetes",
               "helm": "helm", "h": "helm"}
    try:
        return aliases[value]
    except KeyError:
        raise argparse.ArgumentTypeError(
            "format must be kubernetes (k8s, k) or helm (h)"
        ) from None


def _render_helm(application, base_dir: Path) -> str:
    values = HelmRenderer().render(application, base_dir)
    return yaml.safe_dump(values, sort_keys=False)


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
        help="Generate Kubernetes manifests or Helm values from an application definition",
        description="Render Kubernetes manifests or Helm values YAML to stdout or an output file.",
    )

    render_parser.add_argument(
        "file",
        help="Path to the application YAML file",
    )

    render_parser.add_argument("-o", "--output", help="Write generated YAML to this file")
    render_parser.add_argument(
        "-f", "--format", dest="renderer", type=_format_name, default="kubernetes",
        metavar="FORMAT",
        help="Format: kubernetes | k8s | k (default: kubernetes), or helm | h (Helm values)",
    )
    render_parser.add_argument("-n", "--name", help="Override the application name")
    render_parser.add_argument(
        "-c", "--chart", metavar="PATH",
        help="External chart to inspect (required for Helm; not used for rendering yet)",
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "render":
        if args.renderer == "helm" and args.chart is None:
            parser.error("--chart is required for Helm format")
        if args.renderer != "helm" and args.chart is not None:
            parser.error("--chart is only supported for Helm format")

    if args.command in {"validate", "render"}:
        try:
            application = load_application(args.file)
            if args.command == "render" and args.name is not None:
                data = application.model_dump(by_alias=True)
                data["name"] = args.name
                try:
                    application = Application.model_validate(data)
                except ValidationError as exc:
                    raise ApplicationParseError(
                        "Invalid application definition:\n"
                        + "\n".join(
                            f"{'.'.join(map(str, error['loc']))}: {error['msg']}"
                            for error in exc.errors(include_input=False)
                        )
                    ) from exc

        except ApplicationParseError as exc:
            print(f"Validation failed:\n{exc}", file=sys.stderr)
            return 1

        if args.command == "validate":
            print(f"Application '{application.name}' is valid.")
            return 0

        try:
            base_dir = Path(args.file).resolve().parent
            if args.renderer == "helm":
                # Inspection returns structured notes; presentation is deferred.
                inspect_chart(args.chart, application)
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

        except (ValueError, OSError, NotImplementedError) as exc:
            print(f"Render failed:\n{exc}", file=sys.stderr)
            return 1

        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
