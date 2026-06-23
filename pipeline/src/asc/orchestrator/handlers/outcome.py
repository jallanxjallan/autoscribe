"""Handle task outcomes posted to the orchestrator inbox.

The inbox key kind is deliberately generic: ``outcome:<identity>``.  Once the
outcome record is loaded, routing is based on the outcome fields:

    package  which package executed the task
    action   which task action completed
    result   success/failure

For this smoke target, successful scrivener ``write_call`` outcomes dispatch the
first materialized Step to the worker queue.  The Worker task carries the Call
key plus the Step key, not the Plan key.
"""

from asc.models.process.cursor import Cursor
from asc.models.process.task import Outcome
from asc.redis.key import RedisKey
from asc.scrivener import inbox as scrivener_inbox
from asc.state.calls import CallIndex
from asc.worker import inbox as worker_inbox

from ..contracts import (
    SCRIVENER_CALL_COMPLETED,
    SCRIVENER_CALL_FAILED,
    SCRIVENER_WRITE_CALL,
    SCRIVENER_WRITE_STEP,
    WORKER_EXECUTE_STEP,
)
from ..errors import OrchestratorContractError
from ..tasks import make_scrivener_call_completed, make_worker_step


def handle(key: RedisKey) -> None:
    outcome = Outcome.load(_outcome_key(key))

    if outcome.result == "failure":
        _handle_failed_outcome(outcome)
        return

    if outcome.result != "success":
        raise OrchestratorContractError(
            f"unknown outcome result {outcome.result!r}: {outcome.raw_key}"
        )

    if outcome.package == "scrivener":
        _handle_scrivener_success(outcome)
        return

    if outcome.package == "worker":
        _handle_worker_success(outcome)
        return

    raise OrchestratorContractError(
        f"unknown outcome package {outcome.package!r}: {outcome.raw_key}"
    )


def _outcome_key(key: RedisKey) -> str:
    if getattr(key, "suffix", ""):
        return str(key)
    return Outcome.key_for_identity(key.identity)


def _handle_scrivener_success(outcome: Outcome) -> None:
    if outcome.action == SCRIVENER_WRITE_CALL:
        _dispatch_first_worker_step(outcome)
        return

    if outcome.action == SCRIVENER_WRITE_STEP:
        # Later this should queue the next materialized worker step or call_completed.
        return

    if outcome.action in {SCRIVENER_CALL_COMPLETED, SCRIVENER_CALL_FAILED}:
        return

    raise OrchestratorContractError(
        f"unknown scrivener outcome action {outcome.action!r}: {outcome.raw_key}"
    )


def _dispatch_first_worker_step(outcome: Outcome) -> None:
    cursor_key = _required_text(getattr(outcome, "cursor_key", None), "outcome.cursor_key")
    cursor = Cursor.load(cursor_key)
    call_index = CallIndex.from_identity(cursor.identity)
    step_key = _next_step_key(call_index)

    if step_key is None:
        task = make_scrivener_call_completed(cursor=cursor, completed_after_step=0)
        task.save()
        scrivener_inbox.post(str(task.redis_key))
        return

    step_number = _slot_for_key(call_index, step_key)
    task = make_worker_step(
        call_key=str(cursor.call_key),
        step_key=step_key,
        step_number=step_number,
        cursor_key=cursor_key,
    )
    task.save()
    worker_inbox.post(str(task.redis_key))


def _handle_worker_success(outcome: Outcome) -> None:
    if outcome.action == WORKER_EXECUTE_STEP:
        # Worker routing after the first task is deliberately parked for this smoke test.
        return

    raise OrchestratorContractError(
        f"unknown worker outcome action {outcome.action!r}: {outcome.raw_key}"
    )


def _handle_failed_outcome(outcome: Outcome) -> None:
    # For now, fail loud but with task semantics in the message.
    raise OrchestratorContractError(
        f"task outcome failed: package={outcome.package!r} "
        f"action={outcome.action!r} key={outcome.raw_key}"
    )


def _next_step_key(call_index: CallIndex) -> str | None:
    for slot, key in _ordered_slots(call_index):
        if slot == 0:
            continue
        key = str(key).strip()
        if key and RedisKey(key).kind == "step":
            return key
    return None


def _slot_for_key(call_index: CallIndex, expected_key: str) -> int:
    for slot, key in _ordered_slots(call_index):
        if str(key).strip() == expected_key:
            return slot
    raise OrchestratorContractError(
        f"call index does not contain step key {expected_key!r}: {call_index.redis_key}"
    )


def _ordered_slots(call_index: CallIndex) -> list[tuple[int, object]]:
    return sorted(
        ((int(slot), key) for slot, key in call_index.slots().items()),
        key=lambda item: item[0],
    )


def _required_text(value: object, field_name: str) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        raise OrchestratorContractError(f"{field_name} must be non-empty")
    return text


__all__ = ["handle"]
