"""Active-call state-machine for the orchestrator.

The orchestrator no longer consumes initial call notices or outcome messages.
The active zset points at call records; each call already has a call index built
by enqueue. The orchestrator inspects that index and dispatches tasks according
to the artifacts that exist.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from asc.redis.key import RedisKey
from asc.redis.primitives import hashes
from asc.redis.primitives.keys import exists
from asc.scrivener import inbox as scrivener_inbox
from asc.worker import inbox as worker_inbox

from .contracts import (
    SCRIVENER_CALL_COMPLETED,
    SCRIVENER_CALL_FAILED,
    SCRIVENER_WRITE_CALL,
    SCRIVENER_WRITE_STEP,
    WORKER_EXECUTE_STEP,
)
from .errors import OrchestratorContractError
from .handlers import call_index
from .tasks import (
    make_scrivener_call_completed,
    make_scrivener_call_failed,
    make_scrivener_write_call,
    make_scrivener_write_step,
    make_worker_step,
    save_task,
)

SCRIVENER_PACKAGE = "scrivener"
WORKER_PACKAGE = "worker"
TASK_KIND = "task"
COMMITTED_KIND = "committed"
FAILURE_KIND = "failure"


@dataclass(frozen=True, slots=True)
class TaskState:
    key: str
    package: str
    action: str
    data_key: str
    expected_key: str
    failure_key: str | None
    step_key: str | None

    @property
    def expected_exists(self) -> bool:
        return exists(RedisKey(self.expected_key))

    @property
    def failure_exists(self) -> bool:
        return self.failure_key is not None and exists(RedisKey(self.failure_key))


def handle(call_key: str | RedisKey) -> bool:
    """Inspect one active call and dispatch the next required task.

    Returns True while the call should remain in the active zset, and False when
    the call is terminal and should be removed.
    """

    call_record_key = _canonical_call_record_key(call_key)
    index = call_index.for_call_key(call_record_key)

    slot0 = call_index.get_slot(index, 0)
    slot0_kind = RedisKey(slot0).kind

    if slot0_kind == "call":
        _dispatch_scrivener_write_call(index=index, call_key=slot0)
        return True

    if slot0_kind == TASK_KIND:
        state = _load_task(slot0)
        result = _apply_task_state(
            call_identity=RedisKey(call_record_key).identity,
            index=index,
            slot=0,
            state=state,
        )
        if result is not None:
            return result
        return True

    if slot0_kind == FAILURE_KIND:
        return False

    if slot0_kind not in {COMMITTED_KIND}:
        raise OrchestratorContractError(
            f"call index slot 0 must be call/task/committed/failure; got {slot0!r}"
        )

    return _advance_steps(index, call_identity=RedisKey(call_record_key).identity)


def _advance_steps(index, *, call_identity: str) -> bool:
    process_slot = call_index.first_process_slot(index)
    if process_slot is None:
        return False

    slot, value = process_slot
    kind = RedisKey(value).kind

    if kind == "step":
        _dispatch_worker_step(
            call_identity=call_identity,
            index=index,
            slot=slot,
            step_key=value,
        )
        return True

    if kind == TASK_KIND:
        state = _load_task(value)
        result = _apply_task_state(
            call_identity=call_identity,
            index=index,
            slot=slot,
            state=state,
        )
        if result is not None:
            return result
        return True

    if kind in call_index.RESULT_KINDS:
        return _advance_from_persisted_result(
            call_identity=call_identity,
            index=index,
            slot=slot,
            result_key=value,
        )

    raise OrchestratorContractError(
        f"unexpected process slot value at {slot}: {value!r}"
    )


def _apply_task_state(
    *,
    index,
    slot: int,
    state: TaskState,
    call_identity: str,
) -> bool | None:
    if state.failure_exists:
        call_index.set_slot(index, slot, state.failure_key or "")
        return _handle_failure_artifact(index=index, slot=slot, failure_key=state.failure_key or "")

    if not state.expected_exists:
        return None

    if state.package == SCRIVENER_PACKAGE:
        return _apply_scrivener_success(
            index=index,
            slot=slot,
            state=state,
            call_identity=call_identity,
        )

    if state.package == WORKER_PACKAGE:
        return _apply_worker_success(index=index, slot=slot, state=state)

    raise OrchestratorContractError(
        f"unknown task package {state.package!r}: {state.key}"
    )


def _apply_scrivener_success(
    *,
    index,
    slot: int,
    state: TaskState,
    call_identity: str,
) -> bool:
    if state.action == SCRIVENER_WRITE_CALL:
        call_index.set_slot(index, slot, state.expected_key)
        return _advance_steps(index, call_identity=call_identity)

    if state.action == SCRIVENER_WRITE_STEP:
        # The committed artifact proves the ledger write happened. Keep the
        # result/failure artifact in the step slot so the next worker step can
        # use it as data.
        call_index.set_slot(index, slot, state.data_key)
        return _advance_from_persisted_result(
            index=index,
            slot=slot,
            result_key=state.data_key,
            call_identity=call_identity,
        )

    if state.action in {SCRIVENER_CALL_COMPLETED, SCRIVENER_CALL_FAILED}:
        call_index.set_slot(index, slot, state.expected_key)
        return False

    raise OrchestratorContractError(
        f"unknown scrivener task action {state.action!r}: {state.key}"
    )


def _apply_worker_success(*, index, slot: int, state: TaskState) -> bool:
    if state.action != WORKER_EXECUTE_STEP:
        raise OrchestratorContractError(
            f"unknown worker task action {state.action!r}: {state.key}"
        )

    _dispatch_scrivener_write_step(index=index, slot=slot, result_key=state.expected_key)
    return True


def _handle_failure_artifact(*, index, slot: int, failure_key: str) -> bool:
    key = RedisKey(failure_key)
    if key.kind != FAILURE_KIND:
        raise OrchestratorContractError(f"failure artifact must be failure:*; got {failure_key!r}")

    if slot == 0:
        # Ledger failure while writing the call itself has no safe continuation.
        return False

    _dispatch_scrivener_write_step(index=index, slot=slot, result_key=failure_key)
    return True


def _advance_from_persisted_result(
    *,
    index,
    slot: int,
    result_key: str,
    call_identity: str,
) -> bool:
    result = RedisKey(result_key)

    if result.kind == FAILURE_KIND:
        _dispatch_terminal_failure(index=index, slot=slot, result_key=result_key)
        return True

    if result.kind not in {"response", "transform", "retrieval"}:
        raise OrchestratorContractError(
            f"step result must be response/transform/retrieval/failure; got {result_key!r}"
        )

    next_step = call_index.next_step_slot(index, slot)
    if next_step is not None:
        next_slot, step_key = next_step
        _dispatch_worker_step(
            index=index,
            slot=next_slot,
            step_key=step_key,
            call_identity=call_identity,
        )
        return True

    _dispatch_terminal_success(index=index, slot=slot, result_key=result_key)
    return True


def _dispatch_scrivener_write_call(*, index, call_key: str) -> None:
    task = make_scrivener_write_call(data_key=call_key)
    task_key = save_task(task)
    call_index.set_slot(index, 0, task_key)
    scrivener_inbox.post(task_key)


def _dispatch_worker_step(
    *,
    index,
    slot: int,
    step_key: str,
    call_identity: str,
) -> None:
    call_index.validate_step_slot(step_key=step_key, slot=slot)
    data_key = call_index.data_key_for_step(
        call_identity=call_identity,
        call_index=index,
        slot=slot,
    )
    task = make_worker_step(step_key=step_key, data_key=data_key)
    task_key = save_task(task)
    call_index.set_slot(index, slot, task_key)
    worker_inbox.post(task_key)


def _dispatch_scrivener_write_step(*, index, slot: int, result_key: str) -> None:
    task = make_scrivener_write_step(data_key=result_key)
    task_key = save_task(task)
    call_index.set_slot(index, slot, task_key)
    scrivener_inbox.post(task_key)


def _dispatch_terminal_success(*, index, slot: int, result_key: str) -> None:
    task = make_scrivener_call_completed(data_key=result_key)
    task_key = save_task(task)
    call_index.set_slot(index, slot, task_key)
    scrivener_inbox.post(task_key)


def _dispatch_terminal_failure(*, index, slot: int, result_key: str) -> None:
    task = make_scrivener_call_failed(data_key=result_key)
    task_key = save_task(task)
    call_index.set_slot(index, slot, task_key)
    scrivener_inbox.post(task_key)


def _load_task(task_key: str) -> TaskState:
    key = RedisKey(task_key)
    if key.kind != TASK_KIND:
        raise OrchestratorContractError(f"expected task key; got {task_key!r}")

    raw = hashes.hgetall(key)
    if not raw:
        raise OrchestratorContractError(f"missing task hash: {task_key}")

    return TaskState(
        key=task_key,
        package=_required(raw, "package", task_key),
        action=_required(raw, "action", task_key),
        data_key=_required(raw, "data_key", task_key),
        expected_key=_required(raw, "expected_key", task_key),
        failure_key=_optional(raw, "failure_key"),
        step_key=_optional(raw, "step_key"),
    )


def _required(raw: Mapping[str, str], field: str, task_key: str) -> str:
    value = _optional(raw, field)
    if value is None:
        raise OrchestratorContractError(f"task {task_key} missing required field: {field}")
    return value


def _optional(raw: Mapping[str, str], field: str) -> str | None:
    value = raw.get(field)
    text = "" if value is None else str(value).strip()
    return text or None


def _canonical_call_record_key(key: str | RedisKey) -> str:
    parsed = RedisKey(str(key))
    if parsed.kind != "call":
        raise OrchestratorContractError(f"active zset member must be call key: {key!r}")
    if parsed.suffix:
        return str(parsed)
    return RedisKey(kind="call", identity=parsed.identity, suffix="record").raw_key


__all__ = ["handle"]
