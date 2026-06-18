"""Redis-backed response index.

Key shape:

    response:<call_ulid>:index

Slot meaning:

    slot 0  = original call record key
    slot 1  = step 1 marker/result/failure key
    slot 2  = step 2 marker/result/failure key
    ...

The response index is only a three-state slot ledger:

    empty string  -> not yet dispatched
    marker key    -> step is in flight
    produced key  -> step completed

It does not know what marker or produced keys contain.
"""

from __future__ import annotations

from typing import Any, ClassVar

from asc.redis.index_base import RedisIndex
from asc.redis.key import RedisKey


RESPONSE_INDEX_KIND = "response"
RESPONSE_INDEX_SUFFIX = "index"
EMPTY_RESPONSE_SLOT = ""


def create_response_index(
    identity: str,
    *,
    call_key: str,
    total_steps: int,
    ttl_seconds: int | None = None,
) -> str:
    """Create a response index and return its Redis key.

    ``identity`` is the call ULID / process identity.
    """

    index = ResponseIndex.from_identity(identity)
    index.initialize(
        call_key=call_key,
        total_steps=total_steps,
        ttl_seconds=ttl_seconds,
    )
    return str(index)


class ResponseIndex(RedisIndex):
    """Redis HASH adapter for response-index slots."""

    KIND: ClassVar[str] = RESPONSE_INDEX_KIND
    SUFFIX: ClassVar[str] = RESPONSE_INDEX_SUFFIX

    @classmethod
    def key_for(cls, identity: str) -> str:
        """Return the response-index key for a call/process identity."""

        clean_identity = cls._require_text(identity, field_name="identity")
        return str(
            RedisKey(
                kind=cls.KIND,
                identity=clean_identity,
                suffix=cls.SUFFIX,
            )
        )

    @classmethod
    def from_identity(cls, identity: str) -> ResponseIndex:
        """Bind a response index from a call/process identity."""

        return cls(cls.key_for(identity))

    def initialize(
        self,
        *,
        call_key: str,
        total_steps: int,
        ttl_seconds: int | None = None,
    ) -> None:
        """Initialize response slots.

        Existing contents are deleted first.

        Slot 0 receives the original call key.
        Slots 1..total_steps are initialized as empty strings.
        """

        source_key = self._require_text(call_key, field_name="call_key")
        steps = _required_int(total_steps, "total_steps")

        if steps < 0:
            raise ValueError("total_steps must be >= 0")

        self.delete()

        self.key.hset(field="0", value=source_key)

        for slot in range(1, steps + 1):
            self.key.hset(field=str(slot), value=EMPTY_RESPONSE_SLOT)

        if ttl_seconds is not None:
            self._r().expire(str(self.key), int(ttl_seconds))

    def slots(self) -> dict[int, str]:
        """Return all slots as ``{slot_number: key_text}``."""

        raw = self.key.hgetall()

        slots: dict[int, str] = {}
        for raw_slot, raw_value in raw.items():
            slot_text = _decode(raw_slot).strip()
            if not slot_text:
                continue

            try:
                slot = int(slot_text)
            except ValueError as exc:
                raise ValueError(
                    f"invalid response index slot {slot_text!r}: {self.key}"
                ) from exc

            slots[slot] = _decode(raw_value).strip()

        return dict(sorted(slots.items()))

    def get_slot(self, slot: int) -> str | None:
        """Return a slot value, or ``None`` if the slot does not exist."""

        slot_number = _required_int(slot, "slot")
        value = self.key.hget(str(slot_number))

        if value is None:
            return None

        return _decode(value).strip()

    def set_slot(self, slot: int, value: str) -> None:
        """Set an existing slot to ``value``."""

        slot_number = _required_int(slot, "slot")
        text = self._require_text(value, field_name="value")

        if not self.exists():
            raise ValueError(f"response index does not exist: {self.key}")

        if self.get_slot(slot_number) is None:
            raise ValueError(f"response index missing slot {slot_number}: {self.key}")

        self.key.hset(field=str(slot_number), value=text)

    def input_key_for_step(self, step_number: int) -> str:
        """Return the input key for a worker step.

        Step 1 reads slot 0.
        Step 2 reads slot 1.
        Step N reads slot N - 1.
        """

        step = _required_int(step_number, "step_number")

        if step < 1:
            raise ValueError("step_number must be >= 1")

        previous_slot = step - 1
        value = self.get_slot(previous_slot)

        if value is None:
            raise ValueError(
                f"response index missing input slot {previous_slot}: {self.key}"
            )

        text = value.strip()
        if not text:
            raise ValueError(
                f"response index input slot {previous_slot} is empty: {self.key}"
            )

        return text

    def claim_slot(self, slot: int, marker_key: str) -> None:
        """Move a slot from empty to in-flight marker.

        Mechanical transition:

            empty -> marker
        """

        slot_number = _required_int(slot, "slot")
        marker = self._require_text(marker_key, field_name="marker_key")

        current = self.get_slot(slot_number)
        if current is None:
            raise ValueError(f"response index missing slot {slot_number}: {self.key}")

        if current.strip():
            raise ValueError(
                "response index slot is already occupied: "
                f"slot={slot_number} value={current!r} index={self.key}"
            )

        self.set_slot(slot_number, marker)

    def complete_slot(
        self,
        slot: int,
        *,
        expected_marker_key: str,
        produced_key: str,
    ) -> None:
        """Move a slot from expected marker to produced key.

        Guardrail transition:

            expected_marker -> produced_key
        """

        slot_number = _required_int(slot, "slot")
        expected = self._require_text(
            expected_marker_key,
            field_name="expected_marker_key",
        )
        produced = self._require_text(produced_key, field_name="produced_key")

        current = self.get_slot(slot_number)
        if current is None:
            raise ValueError(f"response index missing slot {slot_number}: {self.key}")

        actual = current.strip()
        if actual != expected:
            raise ValueError(
                "response index slot marker mismatch: "
                f"slot={slot_number} expected={expected!r} "
                f"actual={actual!r} index={self.key}"
            )

        self.set_slot(slot_number, produced)

    def next_empty_slot(self) -> int | None:
        """Return the next empty slot, or ``None`` if all slots are occupied."""

        slots = self.slots()
        if not slots:
            raise ValueError(f"response index is missing or empty: {self.key}")

        for slot in sorted(slots):
            if not str(slots[slot]).strip():
                return slot

        return None

    def is_complete(self) -> bool:
        """Return True if no slots are empty."""

        return self.next_empty_slot() is None

    def last_filled_key(self) -> str:
        """Return the last contiguous non-empty slot value."""

        slots = self.slots()
        if not slots:
            raise ValueError(f"response index is missing or empty: {self.key}")

        last = ""
        for slot in sorted(slots):
            value = str(slots[slot]).strip()
            if not value:
                break
            last = value

        if not last:
            raise ValueError(f"response index has no filled slots: {self.key}")

        return last


def _required_int(value: Any, field_name: str) -> int:
    try:
        return int(value)
    except TypeError as exc:
        raise ValueError(f"{field_name} must be an integer") from exc
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an integer") from exc


def _decode(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


__all__ = [
    "EMPTY_RESPONSE_SLOT",
    "RESPONSE_INDEX_KIND",
    "RESPONSE_INDEX_SUFFIX",
    "ResponseIndex",
    "create_response_index",
]