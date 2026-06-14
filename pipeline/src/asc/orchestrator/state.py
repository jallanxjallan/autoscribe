from __future__ import annotations

from typing import Any

from asc.models.runtime.cursor import RuntimeCursor
from asc.orchestrator.errors import OrchestratorContractError
from asc.runtime.response_index import next_empty_response_slot, response_index_complete


def load_cursor(cursor_key: str) -> RuntimeCursor:
    return RuntimeCursor.load(cursor_key)


def save_cursor(cursor: RuntimeCursor) -> None:
    cursor.save()


def cursor_key(cursor: RuntimeCursor) -> str:
    return required_str(cursor, "key")


def is_terminal_cursor(cursor: RuntimeCursor) -> bool:
    """Return true when every fixed response slot is filled."""
    return response_index_complete(cursor.response_index_key)


def advance_cursor(cursor: RuntimeCursor) -> RuntimeCursor:
    """Advance to the next empty response slot.

    Slot 0 is the original call. Slot N is the output for step N, so the next
    empty slot number is also the next worker step number.
    """
    next_slot = next_empty_response_slot(cursor.response_index_key)
    if next_slot is None:
        raise OrchestratorContractError(
            f"cannot advance complete cursor {cursor.identity}: response index full"
        )
    if next_slot < 1:
        raise OrchestratorContractError(
            f"invalid next response slot for cursor {cursor.identity}: {next_slot}"
        )

    cursor.current_step = int(next_slot)
    cursor.save()
    return cursor


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
    "advance_cursor",
    "cursor_key",
    "is_terminal_cursor",
    "load_cursor",
    "required_str",
    "save_cursor",
]
