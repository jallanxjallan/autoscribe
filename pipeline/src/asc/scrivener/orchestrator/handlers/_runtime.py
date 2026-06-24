"""Shared routing helpers for orchestrator handlers."""

from asc.redis.key import RedisKey
from asc.state.calls import CallIndex

from ..errors import OrchestratorContractError


def call_index_for_data_key(data_key: str) -> CallIndex:
    """Load the call index that belongs to a call data key."""

    key = RedisKey(required_text(data_key, "outcome.data_key"))
    if key.kind != "call":
        raise OrchestratorContractError(
            f"outcome data_key must be a call key; got {data_key!r}"
        )
    return CallIndex.from_identity(key.identity)


def call_key_for_index(call_index: CallIndex) -> str:
    value = call_index.slots().get(0) or call_index.slots().get("0")
    return required_text(value, "call_index[0]")


def first_step_key(call_index: CallIndex) -> str | None:
    return next_step_key_after(call_index, 0)


def next_step_key_after(call_index: CallIndex, current_slot: int) -> str | None:
    for slot, key in sorted(call_index.slots().items(), key=lambda item: int(item[0])):
        slot = int(slot)
        if slot <= current_slot:
            continue
        text = str(key).strip()
        if text and RedisKey(text).kind == "step":
            return text
    return None


def set_result_slot(call_index: CallIndex, *, step_number: int, result_key: str) -> None:
    if step_number < 1:
        raise OrchestratorContractError(
            f"worker outcome step_number must be positive; got {step_number!r}"
        )

    result_key = required_text(result_key, "outcome result/failure key")
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


def required_int(value: object, field_name: str) -> int:
    if value is None or value == "":
        raise OrchestratorContractError(f"{field_name} must be non-empty")
    return int(value)


def required_text(value: object, field_name: str) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        raise OrchestratorContractError(f"{field_name} must be non-empty")
    return text


__all__ = [
    "call_index_for_data_key",
    "call_key_for_index",
    "first_step_key",
    "next_step_key_after",
    "required_int",
    "required_text",
    "set_result_slot",
    "slot_for_key",
]
