"""Secret lookup.

Process environment values take precedence over ~/.secrets.env. The secrets
file is read as data; shell commands and variable expansion are not evaluated.
"""

from __future__ import annotations

import os
from pathlib import Path
import shlex


class SecretError(RuntimeError):
    pass


def secret(*names: str, default: str | None = None) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value not in {None, ""}:
            return value
    path = Path.home() / ".secrets.env"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return default
    values: dict[str, str] = {}
    for line in lines:
        line = line.strip()
        if line.startswith("export "):
            line = line[7:].lstrip()
        name, separator, raw = line.partition("=")
        name = name.strip()
        if not separator or name not in names:
            continue
        try:
            parts = shlex.split(raw, comments=True, posix=True)
        except ValueError:
            raise SecretError(f"Invalid secret assignment for {name} in {path}") from None
        if len(parts) > 1:
            raise SecretError(f"Invalid secret assignment for {name} in {path}")
        values[name] = parts[0] if parts else ""
    for name in names:
        if values.get(name):
            return values[name]
    return default


def require_secret(*names: str) -> str:
    value = secret(*names)
    if value not in {None, ""}:
        return value
    joined = " or ".join(names)
    raise SecretError(f"Missing required secret: set {joined} in the process environment or ~/.secrets.env")


def openai_api_key() -> str:
    return require_secret("OPENAI_API_KEY", "OPEN_AI_KEY")


def anthropic_api_key() -> str:
    return require_secret("ANTHROPIC_API_KEY")


__all__ = [
    "SecretError",
    "anthropic_api_key",
    "openai_api_key",
    "require_secret",
    "secret",
]
