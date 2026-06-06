"""
asc.core.secrets

Simple secret loading for local development and admin use.

Secrets are read from ~/.secrets.env in KEY=VALUE format, then merged into
os.environ only for keys that are not already set in the process environment.

This keeps deployment flexibility intact:
- production can inject real environment variables
- local development can rely on ~/.secrets.env
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

_SECRETS_PATH: Final[Path] = Path("~/.secrets.env").expanduser()
_LOADED: bool = False


class SecretError(RuntimeError):
    """Raised when a required secret is missing or invalid."""


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _parse_env_line(line: str) -> tuple[str, str] | None:
    """
    Parse one KEY=VALUE line from an env file.

    Supports:
    - blank lines
    - comment lines beginning with #
    - optional leading 'export '
    - quoted values
    """
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None

    if stripped.startswith("export "):
        stripped = stripped[7:].lstrip()

    if "=" not in stripped:
        raise SecretError(f"Invalid line in secrets file: {line.rstrip()}")

    key, value = stripped.split("=", 1)
    key = key.strip()
    value = _strip_quotes(value.strip())

    if not key:
        raise SecretError(f"Empty key in secrets file: {line.rstrip()}")

    return key, value


def load_secrets(path: Path | None = None) -> None:
    """
    Load secrets from ~/.secrets.env into os.environ once.

    Existing environment variables always win. This lets production or shell-
    provided variables override the local file naturally.
    """
    global _LOADED

    if _LOADED:
        return

    secrets_path = (path or _SECRETS_PATH).expanduser()

    if not secrets_path.exists():
        _LOADED = True
        return

    for raw_line in secrets_path.read_text(encoding="utf-8").splitlines():
        parsed = _parse_env_line(raw_line)
        if parsed is None:
            continue

        key, value = parsed
        os.environ.setdefault(key, value)

    _LOADED = True


def get_secret(name: str, *, default: str | None = None) -> str | None:
    """
    Return a secret value, loading ~/.secrets.env first if needed.

    Returns default if the variable is not set.
    """
    load_secrets()
    return os.environ.get(name, default)


def require_secret(name: str) -> str:
    """
    Return a required secret value or raise SecretError.
    """
    value = get_secret(name)
    if value in {None, ""}:
        raise SecretError(
            f"Required secret '{name}' is missing. "
            f"Set it in the environment or in {_SECRETS_PATH}."
        )
    return value


def get_secret_int(name: str, *, default: int | None = None) -> int | None:
    """
    Return an integer secret value.
    """
    raw = get_secret(name)
    if raw in {None, ""}:
        return default

    try:
        return int(raw)
    except ValueError as exc:
        raise SecretError(f"Secret '{name}' must be an integer.") from exc


def require_secret_int(name: str) -> int:
    """
    Return a required integer secret value or raise SecretError.
    """
    raw = require_secret(name)
    try:
        return int(raw)
    except ValueError as exc:
        raise SecretError(f"Secret '{name}' must be an integer.") from exc


def get_secret_bool(name: str, *, default: bool | None = None) -> bool | None:
    """
    Return a boolean secret/config value.

    Truthy:
        1, true, yes, on

    Falsy:
        0, false, no, off
    """
    raw = get_secret(name)
    if raw in {None, ""}:
        return default

    lowered = raw.strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False

    raise SecretError(f"Secret '{name}' must be a boolean-like value.")


# Optional convenience accessors.
# Add to these as your provider list grows.

def openai_api_key() -> str:
    return require_secret("OPENAI_API_KEY")


def anthropic_api_key() -> str:
    return require_secret("ANTHROPIC_API_KEY")