import argparse
import sys

import yaml

from kubeapp.generators import application_to_helm_values
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
        help="Generate Helm values from an application definition",
    )

    render_parser.add_argument(
        "file",
        help="Path to the application YAML file",
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
            print(
                f"Application '{application.metadata.name}' "
                "is valid."
            )
            return 0

        print(
            yaml.safe_dump(
                application_to_helm_values(application),
                sort_keys=False,
            ),
            end="",
        )
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
