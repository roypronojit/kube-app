import argparse
import sys
from pathlib import Path

import yaml

from kubeapp.manifests import application_to_kubernetes_manifests
from kubeapp.parser import ApplicationParseError, load_application


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
            manifests = application_to_kubernetes_manifests(
                application, Path(args.file).resolve().parent
            )
            rendered = yaml.safe_dump_all(manifests, sort_keys=False)
            if args.output:
                output = Path(args.output)
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(rendered, encoding="utf-8")
            else:
                print(rendered, end="")

        except (ValueError, OSError) as exc:
            print(f"Render failed:\n{exc}", file=sys.stderr)
            return 1

        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
