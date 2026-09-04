"""Source-controlled AutoScribe installation configuration.

All hard-coded, non-secret installation variables belong in this package.
Secrets are read only through :mod:`asc.config.secrets`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .repos import CONTROL
from .runtime import (
    ENGINE_PACKAGES,
    EXTENSIONS_ROOT,
    FAILURE_TTL_SECONDS,
    INSTRUCTION_TTL_SECONDS,
    MIN_REMAINING_INSTRUCTION_TTL_SECONDS,
    REDIS_URL,
    RESPONSE_TTL_SECONDS,
    SCRIPT_PACKAGES,
    SQL_LEDGER_PATH,
)
from .secrets import SecretError, anthropic_api_key, openai_api_key, require_secret, secret


@dataclass(frozen=True)
class Config:
    redis_url: str = REDIS_URL
    sql_ledger_path: Path = SQL_LEDGER_PATH
    extensions_root: Path = EXTENSIONS_ROOT


config = Config()


def ensure_runtime_paths() -> None:
    if not EXTENSIONS_ROOT.is_dir():
        raise FileNotFoundError(f"AutoScribe extensions root not found: {EXTENSIONS_ROOT}")


__all__ = [
    "CONTROL",
    "Config",
    "ENGINE_PACKAGES",
    "EXTENSIONS_ROOT",
    "FAILURE_TTL_SECONDS",
    "INSTRUCTION_TTL_SECONDS",
    "MIN_REMAINING_INSTRUCTION_TTL_SECONDS",
    "REDIS_URL",
    "RESPONSE_TTL_SECONDS",
    "SCRIPT_PACKAGES",
    "SQL_LEDGER_PATH",
    "SecretError",
    "anthropic_api_key",
    "config",
    "ensure_runtime_paths",
    "openai_api_key",
    "require_secret",
    "secret",
]
