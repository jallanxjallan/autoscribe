"""Call-index helpers used by the active-zset orchestrator."""

from asc.redis.key import RedisKey
from asc.state.calls import CallIndex

from ..errors import OrchestratorContractError

RESULT_KINDS = {"response", "transform", "retrieval", "failure"}
DATA_KINDS = {"call", *RESULT_KINDS}
TASK_KIND = "task"
STEP_KIND = "step"
COMMITTED_KIND = "committed"


def for_call_key(call_key: str | RedisKey) -> CallIndex:
    key = RedisKey(str(call_key))
    if key.kind != "call":
        raise OrchestratorContractError(f"active member must be a call key: {call_key!r}")
    return CallIndex.from_identity(key.identity)


def slots(call_index: CallIndex) -> dict[int, str]:
    return {
        int(slot): str(value).strip()
        for slot, value in call_index.slots().items()
        if str(value).strip()
    }


def get_slot(call_index: CallIndex, slot: int) -> str:
    value = call_index.slots().get(slot) or call_index.slots().get(str(slot))
    return required_text(value, f"call_index[{slot}]")


def set_slot(call_index: CallIndex, slot: int, key: str | RedisKey) -> None:
    call_index.set_slot(int(slot), str(key).strip())


def first_process_slot(call_index: CallIndex) -> tuple[int, str] | None:
    for slot, value in sorted(slots(call_index).items()):
        if slot == 0:
            continue
        kind = RedisKey(value).kind
        if kind in {STEP_KIND, TASK_KIND, *RESULT_KINDS}:
            return slot, value
    return None


def next_step_slot(call_index: CallIndex, current_slot: int) -> tuple[int, str] | None:
    next_slot = current_slot + 1
    value = call_index.slots().get(next_slot) or call_index.slots().get(str(next_slot))
    if value is None or str(value).strip() == "":
        return None

    text = str(value).strip()
    if RedisKey(text).kind != STEP_KIND:
        raise OrchestratorContractError(
            f"call_index[{next_slot}] must be a step key or absent; got {text!r}"
        )

    validate_step_slot(step_key=text, slot=next_slot)
    return next_slot, text


def data_key_for_step(*, call_identity: str, call_index: CallIndex, slot: int) -> str:
    if slot < 1:
        raise OrchestratorContractError(f"step slot must be >= 1; got {slot}")

    if slot == 1:
        return RedisKey(kind="call", identity=call_identity, suffix="record").raw_key

    previous_slot = slot - 1
    previous_key = get_slot(call_index, previous_slot)
    previous_kind = RedisKey(previous_key).kind
    if previous_kind not in RESULT_KINDS:
        raise OrchestratorContractError(
            f"call_index[{previous_slot}] must be a result data key before step {slot}; "
            f"got {previous_key!r}"
        )

    return previous_key


def validate_step_slot(*, step_key: str, slot: int) -> None:
    key = RedisKey(step_key)
    if key.kind != STEP_KIND:
        raise OrchestratorContractError(f"call_index[{slot}] must be a step key; got {step_key!r}")

    suffix = required_text(key.suffix, f"step key suffix for call_index[{slot}]")
    if suffix != str(slot):
        raise OrchestratorContractError(
            f"step suffix must match call index slot: slot {slot}, key {step_key!r}"
        )


def required_text(value: object, field_name: str) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        raise OrchestratorContractError(f"{field_name} must be non-empty")
    return text


__all__ = [
    "COMMITTED_KIND",
    "DATA_KINDS",
    "RESULT_KINDS",
    "STEP_KIND",
    "TASK_KIND",
    "first_process_slot",
    "for_call_key",
    "get_slot",
    "data_key_for_step",
    "next_step_slot",
    "validate_step_slot",
    "required_text",
    "set_slot",
    "slots",
]
