from __future__ import annotations

from typing import Any

from asc.models.runtime.call import CallRecord
from asc.models.runtime.cursor import RuntimeCursor
from asc.orchestrator.errors import OrchestratorContractError


def load_cursor(cursor_key: str) -> RuntimeCursor:
    return RuntimeCursor.load(cursor_key)


def save_cursor(cursor: RuntimeCursor) -> None:
    cursor.save()


def cursor_key(cursor: RuntimeCursor) -> str:
    return required_str(cursor, "key")


def call_key(cursor: RuntimeCursor) -> str:
    return required_str(cursor, "call_key")


def call_record(cursor: RuntimeCursor) -> CallRecord:
    return CallRecord.load(call_key(cursor))


def status(cursor: RuntimeCursor) -> str:
    value = getattr(cursor, "status", None)
    return str(value).strip().lower() if value is not None else ""


def set_status(cursor: RuntimeCursor, value: str) -> None:
    setattr(cursor, "status", value)


def worker_status(cursor: RuntimeCursor) -> str:
    value = getattr(cursor, "worker_status", None)
    return str(value).strip().lower() if value is not None else ""


def clear_worker_outcome(cursor: RuntimeCursor) -> None:
    setattr(cursor, "worker_status", "")
    setattr(cursor, "worker_message", "")
    setattr(cursor, "failure_type", "")
    setattr(cursor, "failure_message", "")


def failure_message(cursor: RuntimeCursor) -> str:
    value = getattr(cursor, "failure_message", None)
    return str(value) if value else "worker reported failure"


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
    "call_key",
    "call_record",
    "clear_worker_outcome",
    "cursor_key",
    "failure_message",
    "load_cursor",
    "required_str",
    "save_cursor",
    "set_status",
    "status",
    "worker_status",
]
