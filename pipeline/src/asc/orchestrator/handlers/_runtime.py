"""Shared routing helpers for orchestrator handlers.

These helpers keep response/failure routing tied to runtime state instead of to
handler-local assumptions. They do not own canonical state; they load the posted
record, verify that its key is present in the call index, and derive the next
route from that index.
"""

from importlib import import_module
from typing import Any

from asc.models.process.cursor import Cursor
from asc.redis.key import RedisKey
from asc.state.calls import CallIndex

from ..errors import OrchestratorContractError


RECORD_CLASS_MODULES = {
    "Response": (
        "asc.models.process.result",
        "asc.models.process.response",
        "asc.models.process.task",
    ),
    "Failure": (
        "asc.models.process.result",
        "asc.models.process.failure",
        "asc.models.process.task",
    ),
}


def load_process_record(key: RedisKey, class_name: str) -> Any:
    """Load a process record without baking in a transitional import path."""

    cls = _record_class(class_name)
    return cls.load(str(key))


def cursor_from_record(record: Any, *, field_name: str) -> Cursor:
    cursor_key = required_text(getattr(record, "cursor_key", None), field_name)
    return Cursor.load(cursor_key)


def call_index_for_cursor(cursor: Cursor) -> CallIndex:
    return CallIndex.from_identity(cursor.identity)


def call_key_for_cursor(cursor: Cursor, call_index: CallIndex) -> str:
    """Return the call key for a cursor, preferring explicit cursor state."""

    value = getattr(cursor, "call_key", None)
    if value not in (None, ""):
        return str(value)

    slots = call_index.slots()
    value = slots.get(0) or slots.get("0")
    return required_text(value, "call_index[0]")


def slot_for_key(call_index: CallIndex, expected_key: str | RedisKey) -> int:
    expected = str(expected_key).strip()
    for slot, key in call_index.slots().items():
        if str(key).strip() == expected:
            return int(slot)
    raise OrchestratorContractError(
        f"call index does not contain key {expected!r}: {call_index.redis_key}"
    )


def next_step_key_after(call_index: CallIndex, current_slot: int) -> str | None:
    for slot, key in sorted(call_index.slots().items()):
        slot = int(slot)
        if slot <= current_slot:
            continue
        text = str(key).strip()
        if text and RedisKey(text).kind == "step":
            return text
    return None


def first_step_key(call_index: CallIndex) -> str | None:
    return next_step_key_after(call_index, 0)


def highest_filled_step(call_index: CallIndex) -> int:
    highest = 0
    for slot, key in call_index.slots().items():
        slot = int(slot)
        if slot > 0 and str(key).strip():
            highest = max(highest, slot)
    return highest


def required_text(value: object, field_name: str) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        raise OrchestratorContractError(f"{field_name} must be non-empty")
    return text


def _record_class(class_name: str) -> type[Any]:
    for module_name in RECORD_CLASS_MODULES.get(class_name, ()): 
        try:
            module = import_module(module_name)
        except ModuleNotFoundError:
            continue
        cls = getattr(module, class_name, None)
        if cls is not None:
            return cls
    searched = ", ".join(RECORD_CLASS_MODULES.get(class_name, ()))
    raise OrchestratorContractError(
        f"could not import {class_name} model; searched: {searched}"
    )


__all__ = [
    "call_index_for_cursor",
    "call_key_for_cursor",
    "cursor_from_record",
    "first_step_key",
    "highest_filled_step",
    "load_process_record",
    "next_step_key_after",
    "required_text",
    "slot_for_key",
]
