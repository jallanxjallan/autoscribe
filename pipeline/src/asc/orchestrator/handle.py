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
FAILURE_KIND = "failure"


@dataclass(frozen=True, slots=True)
class HandleResult:
    active: bool
    waiting: bool = False

    def __bool__(self) -> bool:
        return self.active


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


def handle(call_key: str | RedisKey) -> HandleResult:
    """Inspect one active call and dispatch the next required task.

    Returns an active/waiting result. Waiting means the current index slot is a
    task whose expected success/failure artifact does not exist yet.
    """

    call_record_key = _canonical_call_record_key(call_key)
    index = call_index.for_call_key(call_record_key)

    slot0 = call_index.get_slot(index, 0)
    slot0_kind = RedisKey(slot0).kind

    if slot0_kind == "call":
        if not call_index.has_started(index):
            _post_scrivener_write_call(call_key=slot0)
        return _advance_steps(index, call_identity=RedisKey(call_record_key).identity)

    if slot0_kind == FAILURE_KIND:
        return HandleResult(active=False)

    raise OrchestratorContractError(
        f"call index slot 0 must be call/failure; got {slot0!r}"
    )

def _advance_steps(index, *, call_identity: str) -> HandleResult:
    process_slot = call_index.first_process_slot(index)
    if process_slot is None:
        return HandleResult(active=False)

    slot, value = process_slot
    kind = RedisKey(value).kind

    if kind == "step":
        _dispatch_worker_step(
            call_identity=call_identity,
            index=index,
            slot=slot,
            step_key=value,
        )
        return HandleResult(active=True)

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
        return HandleResult(active=True, waiting=True)

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
) -> HandleResult | None:
    if state.failure_exists:
        call_index.set_slot(index, slot, state.failure_key or "")
        return _handle_failure_artifact(index=index, slot=slot, failure_key=state.failure_key or "")

    if not state.expected_exists:
        return None

    if state.package == SCRIVENER_PACKAGE:
        raise OrchestratorContractError(
            f"scrivener task must not occupy call index slot {slot}: {state.key}"
        )

    if state.package == WORKER_PACKAGE:
        return _apply_worker_success(index=index, slot=slot, state=state, call_identity=call_identity)

    raise OrchestratorContractError(
        f"unknown task package {state.package!r}: {state.key}"
    )


def _apply_worker_success(*, index, slot: int, state: TaskState, call_identity: str) -> HandleResult:
    if not state.step_key:
        raise OrchestratorContractError(
            f"worker task missing step_key: {state.key}"
        )
    call_index.validate_step_slot(step_key=state.step_key, slot=slot)

    if state.action != WORKER_EXECUTE_STEP:
        raise OrchestratorContractError(
            f"unknown worker task action {state.action!r}: {state.key}"
        )

    call_index.set_slot(index, slot, state.expected_key)
    _post_scrivener_write_step(result_key=state.expected_key)
    return _advance_from_persisted_result(
        index=index,
        slot=slot,
        result_key=state.expected_key,
        call_identity=call_identity,
    )

def _handle_failure_artifact(*, index, slot: int, failure_key: str) -> HandleResult:
    key = RedisKey(failure_key)
    if key.kind != FAILURE_KIND:
        raise OrchestratorContractError(f"failure artifact must be failure:*; got {failure_key!r}")

    if slot == 0:
        return HandleResult(active=False)

    _post_scrivener_write_step(result_key=failure_key)
    _post_terminal_failure(result_key=failure_key)
    return HandleResult(active=False)

def _advance_from_persisted_result(
    *,
    index,
    slot: int,
    result_key: str,
    call_identity: str,
) -> HandleResult:
    result = RedisKey(result_key)

    if result.kind == FAILURE_KIND:
        _post_terminal_failure(result_key=result_key)
        return HandleResult(active=False)

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
        return HandleResult(active=True)

    _post_terminal_success(result_key=result_key)
    return HandleResult(active=False)


def _post_scrivener_write_call(*, call_key: str) -> None:
    task = make_scrivener_write_call(data_key=call_key)
    task_key = save_task(task)
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


def _post_scrivener_write_step(*, result_key: str) -> None:
    task = make_scrivener_write_step(data_key=result_key)
    task_key = save_task(task)
    scrivener_inbox.post(task_key)


def _post_terminal_success(*, result_key: str) -> None:
    task = make_scrivener_call_completed(data_key=result_key)
    task_key = save_task(task)
    scrivener_inbox.post(task_key)


def _post_terminal_failure(*, result_key: str) -> None:
    task = make_scrivener_call_failed(data_key=result_key)
    task_key = save_task(task)
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


__all__ = ["HandleResult", "handle"]
