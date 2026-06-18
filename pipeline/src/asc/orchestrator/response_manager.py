"""Orchestrator response-chain manager.

This module translates orchestrator concepts into calls on
``asc.state.response_index.ResponseIndex``.

It does not implement Redis index mechanics. The state layer owns:
- key construction
- slot reads/writes
- empty -> marker
- marker -> produced key

The orchestrator owns:
- cursor/task/outcome interpretation
- which step to dispatch next
- which task key acts as the in-flight marker
"""

from __future__ import annotations

from typing import Any

from asc.models.process.in_process import InProcess
from asc.state.response_index import EMPTY_RESPONSE_SLOT, ResponseIndex


def index_key_for_cursor(cursor: Any) -> str:
    """Return the response-index key for a cursor."""

    explicit = getattr(cursor, "response_index_key", None) or getattr(
        cursor,
        "responses_key",
        None,
    )
    if explicit and str(explicit).strip():
        return str(explicit).strip()

    identity = _required_text(getattr(cursor, "identity", None), "cursor.identity")
    return ResponseIndex.key_for(identity)


def input_key_for_step(cursor: Any, step_number: int) -> str:
    """Return the input key for a worker step."""

    return ResponseIndex(index_key_for_cursor(cursor)).input_key_for_step(step_number)


def mark_step_in_flight(
    *,
    cursor: Any,
    step_number: int,
    task_key: str,
    cursor_key: str,
) -> str:
    """Create an in-process marker and claim the response slot.

    Returns the marker key written into the response index.
    """

    step = _required_int(step_number, "step_number")
    marker = InProcess(
        identity=_required_text(getattr(cursor, "identity", None), "cursor.identity"),
        step_number=step,
        task_key=_required_text(task_key, "task_key"),
        cursor_key=_required_text(cursor_key, "cursor_key"),
    )

    marker_key = marker.save()
    ResponseIndex(index_key_for_cursor(cursor)).claim_slot(step, marker_key)

    return marker_key


def record_step_output(
    *,
    cursor: Any,
    step_number: int,
    produced_key: str,
) -> None:
    """Replace an in-process marker with the produced output key."""

    step = _required_int(step_number, "step_number")
    expected_marker_key = str(InProcess.key_for_step(cursor.identity, step))

    ResponseIndex(index_key_for_cursor(cursor)).complete_slot(
        step,
        expected_marker_key=expected_marker_key,
        produced_key=produced_key,
    )


def next_ready_step(cursor: Any) -> int | None:
    """Return the next empty step slot whose previous slot is populated."""

    index = ResponseIndex(index_key_for_cursor(cursor))
    slots = index.slots()

    if not slots:
        raise ValueError(f"response index is missing or empty: {index}")

    for slot in sorted(slots):
        if slot == 0:
            continue

        if not str(slots[slot]).strip():
            previous = slots.get(slot - 1, EMPTY_RESPONSE_SLOT)
            if str(previous).strip():
                return slot

            raise ValueError(f"response index has a gap before slot {slot}: {index}")

    return None


def slots_for_cursor(cursor: Any) -> dict[int, str]:
    """Return response slots for diagnostics/tests."""

    return ResponseIndex(index_key_for_cursor(cursor)).slots()


def _required_text(value: Any, field_name: str) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        raise ValueError(f"{field_name} must be non-empty")
    return text


def _required_int(value: Any, field_name: str) -> int:
    try:
        return int(value)
    except TypeError as exc:
        raise ValueError(f"{field_name} must be an integer") from exc
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an integer") from exc


__all__ = [
    "index_key_for_cursor",
    "input_key_for_step",
    "mark_step_in_flight",
    "next_ready_step",
    "record_step_output",
    "slots_for_cursor",
]