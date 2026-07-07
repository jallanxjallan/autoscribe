from __future__ import annotations

from asc.core.config import ConfigError as SecretError
from asc.core.config import load_secrets, require_secret, secret


def get_secret(name: str, *, default: str | None = None) -> str | None:
    return secret(name, default=default)


def get_secret_int(name: str, *, default: int | None = None) -> int | None:
    raw = get_secret(name)
    if raw in {None, ""}:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise SecretError(f"Secret '{name}' must be an integer.") from exc


def require_secret_int(name: str) -> int:
    raw = require_secret(name)
    try:
        return int(raw)
    except ValueError as exc:
        raise SecretError(f"Secret '{name}' must be an integer.") from exc


def get_secret_bool(name: str, *, default: bool | None = None) -> bool | None:
    raw = get_secret(name)
    if raw in {None, ""}:
        return default
    lowered = raw.strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    raise SecretError(f"Secret '{name}' must be a boolean-like value.")


def openai_api_key() -> str:
    return require_secret("OPENAI_API_KEY", "OPEN_AI_KEY")


def anthropic_api_key() -> str:
    return require_secret("ANTHROPIC_API_KEY")


__all__ = [
    "SecretError",
    "anthropic_api_key",
    "get_secret",
    "get_secret_bool",
    "get_secret_int",
    "load_secrets",
    "openai_api_key",
    "require_secret",
    "require_secret_int",
]
