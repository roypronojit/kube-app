from pathlib import Path

import yaml
from pydantic import ValidationError

from kubeapp.models import Application


class ApplicationParseError(Exception):
    """Raised when an application definition cannot be parsed."""


def load_application(path: str | Path) -> Application:
    file_path = Path(path)

    if not file_path.exists():
        raise ApplicationParseError(f"Application file does not exist: {file_path}")

    if not file_path.is_file():
        raise ApplicationParseError(f"Application path is not a file: {file_path}")

    try:
        with file_path.open("r", encoding="utf-8") as file:
            data = yaml.safe_load(file)

    except yaml.YAMLError as exc:
        raise ApplicationParseError(f"Invalid YAML: {exc}") from exc

    except (OSError, UnicodeError) as exc:
        raise ApplicationParseError(
            f"Cannot read application file: {file_path}"
        ) from exc

    if not isinstance(data, dict):
        raise ApplicationParseError("Application definition must be a YAML object")

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

    except ValueError as exc:
        raise ApplicationParseError(str(exc)) from exc

    return application
