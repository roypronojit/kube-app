from pathlib import Path

import yaml
from pydantic import ValidationError

from kubeapp.models import Application


class ApplicationParseError(Exception):
    """Raised when an application definition cannot be parsed."""


def load_application(path: str | Path) -> Application:
    file_path = Path(path)

    if not file_path.exists():
        raise ApplicationParseError(
            f"Application file does not exist: {file_path}"
        )

    if not file_path.is_file():
        raise ApplicationParseError(
            f"Application path is not a file: {file_path}"
        )

    try:
        with file_path.open("r", encoding="utf-8") as file:
            data = yaml.safe_load(file)

    except yaml.YAMLError as exc:
        raise ApplicationParseError(
            f"Invalid YAML: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise ApplicationParseError(
            "Application definition must be a YAML object"
        )

    try:
        application = Application.model_validate(data)
        application.validate_application()

    except ValidationError as exc:
        raise ApplicationParseError(
            f"Invalid application definition:\n{exc}"
        ) from exc

    except ValueError as exc:
        raise ApplicationParseError(str(exc)) from exc

    return application