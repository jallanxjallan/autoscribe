"""Secret lookup.

Secrets are the sole deliberate process-environment configuration surface.
AutoScribe does not search .env files, shell startup files, or exterior config
files.  Only credential values explicitly present in the process environment
are read here.
"""

from __future__ import annotations

import os


class SecretError(RuntimeError):
    pass


def secret(*names: str, default: str | None = None) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value not in {None, ""}:
            return value
    return default


def require_secret(*names: str) -> str:
    value = secret(*names)
    if value not in {None, ""}:
        return value
    joined = " or ".join(names)
    raise SecretError(f"Missing required secret: set {joined} in the process environment")


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
