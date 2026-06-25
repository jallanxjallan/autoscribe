"""Shared routing helpers for orchestrator handlers."""

from asc.redis.key import RedisKey
from asc.state.calls import CallIndex

from ..errors import OrchestratorContractError


def call_index_for_data_key(data_key: str) -> CallIndex:
    """Load the call index that belongs to a call-derived data key."""

    key = RedisKey(required_text(data_key, "task.data_key"))
    if key.kind not in {"call", "response", "transform", "retrieval", "failure"}:
        raise OrchestratorContractError(
            f"task data_key must be call-derived; got {data_key!r}"
        )
    return CallIndex.from_identity(key.identity)


def call_key_for_index(call_index: CallIndex) -> str:
    value = call_index.slots().get(0) or call_index.slots().get("0")
    return required_text(value, "call_index[0]")


def first_step_key(call_index: CallIndex) -> str | None:
    return next_step_key_after(call_index, 0)


def next_step_key_after(call_index: CallIndex, current_slot: int) -> str | None:
    for slot, key in sorted(call_index.slots().items(), key=lambda item: int(item[0])):
        slot_number = int(slot)
        if slot_number <= current_slot:
            continue
        text = str(key).strip()
        if text and RedisKey(text).kind == "step":
            return text
    return None


def latest_data_key(call_index: CallIndex) -> str:
    """Return the highest filled non-step slot in the call index.

    The call index is the source of process position. Slot 0 is the original
    call record. Step slots start as step keys and are replaced by the result or
    failure key when that step has happened.
    """

    latest_slot = -1
    latest_key = ""
    for slot, key in call_index.slots().items():
        text = str(key).strip()
        if not text:
            continue
        if RedisKey(text).kind == "step":
            continue
        slot_number = int(slot)
        if slot_number > latest_slot:
            latest_slot = slot_number
            latest_key = text

    return required_text(latest_key, "call_index latest data key")


def set_result_slot(call_index: CallIndex, *, step_number: int, result_key: str) -> None:
    if step_number < 1:
        raise OrchestratorContractError(
            f"worker step slot must be positive; got {step_number!r}"
        )

    result_key = required_text(result_key, "outcome.output_key")
    current = call_index.slots().get(step_number) or call_index.slots().get(str(step_number))
    if current and RedisKey(str(current)).kind != "step":
        raise OrchestratorContractError(
            f"call index slot {step_number} is already filled: {current!r}"
        )

    call_index.set_slot(step_number, result_key)


def slot_for_key(call_index: CallIndex, expected_key: str | RedisKey) -> int:
    expected = str(expected_key).strip()
    for slot, key in call_index.slots().items():
        if str(key).strip() == expected:
            return int(slot)
    raise OrchestratorContractError(
        f"call index does not contain key {expected!r}: {call_index.redis_key}"
    )


def required_text(value: object, field_name: str) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        raise OrchestratorContractError(f"{field_name} must be non-empty")
    return text


__all__ = [
    "call_index_for_data_key",
    "call_key_for_index",
    "first_step_key",
    "latest_data_key",
    "next_step_key_after",
    "required_text",
    "set_result_slot",
    "slot_for_key",
]
