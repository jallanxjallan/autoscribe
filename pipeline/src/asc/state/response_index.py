from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from asc.redis.index_base import RedisIndex
from asc.redis.key import RedisKey


EMPTY_RESPONSE_SLOT = ""


class ResponseIndex(RedisIndex):
    """Response-slot index for one call."""

    @classmethod
    def for_identity(cls, identity: str) -> "ResponseIndex":
        return cls(response_index_key(identity))

    def replace_slots(self, mapping: Mapping[int, str]) -> None:
        self.delete()
        self.key.hset(mapping={str(k): str(v) for k, v in mapping.items()})

    def slots(self) -> dict[int, str]:
        return _normalize_slots(self.key.hgetall())

    def get_slot(self, slot: int) -> str | None:
        return self.key.hget(str(int(slot)))

    def set_slot(self, slot: int, value: str) -> None:
        value = self._require_text(value, field_name="value")
        self.key.hset(field=str(int(slot)), value=value)


def response_index_key(identity: str) -> str:
    identity = str(identity).strip()
    if not identity:
        raise ValueError("identity must be non-empty")
    return str(RedisKey.from_parts("response_index", identity, "slots"))


def initialize_response_index(
    *,
    identity: str,
    call_key: str,
    terminal_step: int,
) -> str:
    """Create the fixed response index for one call.

    Slot 0 is the original call key. Each planned step owns the matching output
    slot, so step 1 writes slot 1, step 2 writes slot 2, etc.
    """
    terminal = int(terminal_step)
    if terminal < 1:
        raise ValueError(f"terminal_step must be >= 1, got {terminal_step!r}")

    index = ResponseIndex.for_identity(identity)

    mapping = {0: str(call_key)}
    for slot in range(1, terminal + 1):
        mapping[slot] = EMPTY_RESPONSE_SLOT

    index.replace_slots(mapping)
    return str(index)


def response_index(index_key: str) -> dict[int, str]:
    return ResponseIndex(index_key).slots()


def response_input_key(index_key: str, current_step: int) -> str:
    slot = int(current_step) - 1
    value = ResponseIndex(index_key).get_slot(slot)

    if value is None or not str(value).strip():
        raise ValueError(
            f"response index missing input slot {slot} for step {current_step}: {index_key}"
        )

    return str(value).strip()


def response_output_slot(current_step: int) -> int:
    slot = int(current_step)
    if slot < 1:
        raise ValueError(f"current_step must be >= 1, got {current_step!r}")
    return slot


def response_output_key(identity: str, current_step: int) -> str:
    return str(RedisKey.from_parts("result", str(identity).strip(), f"step.{int(current_step)}"))


def record_response_output(index_key: str, current_step: int, output_key: str) -> None:
    slot = response_output_slot(current_step)
    ResponseIndex(index_key).set_slot(slot, output_key)


def response_index_complete(index_key: str) -> bool:
    slots = response_index(index_key)

    if not slots:
        raise ValueError(f"response index is missing or empty: {index_key}")

    return all(str(value).strip() for value in slots.values())


def next_empty_response_slot(index_key: str) -> int | None:
    slots = response_index(index_key)

    for slot in sorted(slots):
        if not str(slots[slot]).strip():
            return slot

    return None


def _normalize_slots(raw: Mapping[Any, Any]) -> dict[int, str]:
    slots: dict[int, str] = {}

    for key, value in raw.items():
        try:
            slot = int(str(key))
        except (TypeError, ValueError):
            continue

        slots[slot] = "" if value is None else str(value)

    return slots


__all__ = [
    "EMPTY_RESPONSE_SLOT",
    "ResponseIndex",
    "initialize_response_index",
    "next_empty_response_slot",
    "record_response_output",
    "response_index",
    "response_index_complete",
    "response_index_key",
    "response_input_key",
    "response_output_key",
    "response_output_slot",
]