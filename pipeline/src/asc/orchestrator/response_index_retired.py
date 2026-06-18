"""Orchestrator-facing response-index helpers.

This module is intentionally a thin adapter over ``asc.state.response_index``.
The orchestrator should not reach for a Redis client directly; the state layer
owns the Redis index implementation and key mechanics.
"""

from __future__ import annotations

from typing import Any

from asc.state.response_index import (
    EMPTY_RESPONSE_SLOT,
    ResponseIndex,
    response_index,
    response_index_key,
    response_input_key,
)


def load_response_index(cursor: Any) -> str:
    """Return the response-index key for a cursor.

    Current cursors may either carry the response-index key explicitly or rely
    on the standard key derived from the process identity.
    """

    explicit = getattr(cursor, "response_index_key", None) or getattr(cursor, "responses_key", None)
    if explicit and str(explicit).strip():
        return str(explicit).strip()

    identity = _required_text(getattr(cursor, "identity", None), "cursor.identity")
    return response_index_key(identity)


def previous_output_key(index_key: str, step_number: int) -> str:
    """Return the input key for ``step_number`` from the previous slot."""

    return response_input_key(index_key, int(step_number))


def claim_step_slot(index_key: str, *, step_number: int, marker_key: str) -> None:
    """Claim a worker output slot with an in-process marker.

    The slot must be empty. This makes dispatch observable to the watchdog and
    prevents duplicate assignment from silently overwriting another owner.
    """

    slot = int(step_number)
    marker = _required_text(marker_key, "marker_key")
    current = ResponseIndex(index_key).get_slot(slot)

    if current is None:
        raise ValueError(f"response index missing output slot {slot}: {index_key}")

    if str(current).strip():
        raise ValueError(
            f"response index slot {slot} is already claimed: {index_key} -> {current}"
        )

    ResponseIndex(index_key).set_slot(slot, marker)


def replace_step_slot(
    index_key: str,
    *,
    step_number: int,
    expected_marker_key: str,
    produced_key: str,
) -> None:
    """Replace an in-process marker with the worker's result/failure key."""

    slot = int(step_number)
    expected = _required_text(expected_marker_key, "expected_marker_key")
    produced = _required_text(produced_key, "produced_key")

    current = ResponseIndex(index_key).get_slot(slot)
    if current is None:
        raise ValueError(f"response index missing output slot {slot}: {index_key}")

    current_text = str(current).strip()
    if current_text != expected:
        raise ValueError(
            "response index slot owner mismatch: "
            f"slot={slot} expected={expected!r} actual={current_text!r} index={index_key}"
        )

    ResponseIndex(index_key).set_slot(slot, produced)


def index_slots(index_key: str) -> dict[int, str]:
    """Expose normalized slots for diagnostics/tests without Redis-client access."""

    return response_index(index_key)


def next_ready_step(index_key: str) -> int | None:
    """Return the next empty worker slot whose input slot is populated."""

    slots = response_index(index_key)
    if not slots:
        raise ValueError(f"response index is missing or empty: {index_key}")

    for slot in sorted(slots):
        if slot == 0:
            continue
        if not str(slots[slot]).strip():
            previous = slots.get(slot - 1, EMPTY_RESPONSE_SLOT)
            if str(previous).strip():
                return slot
            raise ValueError(
                f"response index has a gap before slot {slot}: {index_key}"
            )

    return None


def _required_text(value: Any, field_name: str) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        raise ValueError(f"{field_name} must be non-empty")
    return text


__all__ = [
    "claim_step_slot",
    "index_slots",
    "load_response_index",
    "next_ready_step",
    "previous_output_key",
    "replace_step_slot",
    "save_response_index",
]
