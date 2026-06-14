from __future__ import annotations

from typing import Any

from asc.models.runtime.cursor import RuntimeCursor
from asc.orchestrator.errors import OrchestratorContractError


def load_cursor(cursor_key: str) -> RuntimeCursor:
    return RuntimeCursor.load(cursor_key)


def save_cursor(cursor: RuntimeCursor) -> None:
    cursor.save()


def cursor_key(cursor: RuntimeCursor) -> str:
    return required_str(cursor, "key")


def required_str(obj: Any, name: str) -> str:
    if not hasattr(obj, name):
        raise OrchestratorContractError(f"{type(obj).__name__} missing required field: {name}")
    value = getattr(obj, name)
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    if not isinstance(value, str) or not value.strip():
        raise OrchestratorContractError(f"{type(obj).__name__}.{name} must be non-empty")
    return value.strip()


__all__ = [
    "cursor_key",
    "load_cursor",
    "required_str",
    "save_cursor",
]
