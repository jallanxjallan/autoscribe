"""Decisions after scrivener tasks complete."""

from asc.models.process.task import Outcome, ScrivenerTask
from asc.redis.key import RedisKey
from asc.scrivener import inbox as scrivener_inbox
from asc.worker import inbox as worker_inbox

from ..contracts import (
    SCRIVENER_CALL_COMPLETED,
    SCRIVENER_CALL_FAILED,
    SCRIVENER_WRITE_CALL,
    SCRIVENER_WRITE_STEP,
)
from ..errors import OrchestratorContractError
from ..tasks import (
    make_scrivener_call_completed,
    make_scrivener_call_failed,
    make_worker_step,
)
from . import call_index

SUCCESS = "success"
FAILURE = "failure"
STEP_RESULT_KINDS = {"response", "transform", "retrieval", "failure"}


def handle_done(*, task: ScrivenerTask, outcome: Outcome) -> None:
    status = call_index.required_text(outcome.status, "outcome.status")
    if status == FAILURE:
        # A failed ledger write has no safe continuation.
        return

    if status != SUCCESS:
        raise OrchestratorContractError(
            f"unknown scrivener outcome status {status!r}: {outcome.raw_key}"
        )

    data_key = RedisKey(call_index.required_text(task.data_key, "task.data_key"))

    if task.action == SCRIVENER_WRITE_CALL:
        if data_key.kind != "call":
            raise OrchestratorContractError(
                "scrivener write_call committed non-call data; refusing to "
                f"restart worker chain: task={task.raw_key} data_key={data_key.raw_key}"
            )
        _dispatch_first_worker_step(task)
        return

    if task.action == SCRIVENER_WRITE_STEP:
        if data_key.kind not in STEP_RESULT_KINDS:
            raise OrchestratorContractError(
                "scrivener write_step committed non-step-result data: "
                f"task={task.raw_key} data_key={data_key.raw_key}"
            )
        _advance_after_step_write(str(data_key))
        return

    if task.action in {SCRIVENER_CALL_COMPLETED, SCRIVENER_CALL_FAILED}:
        if data_key.kind not in STEP_RESULT_KINDS:
            raise OrchestratorContractError(
                "scrivener export terminal action committed non-result data: "
                f"task={task.raw_key} data_key={data_key.raw_key}"
            )
        return

    raise OrchestratorContractError(
        f"unknown scrivener task action {task.action!r}: {task.raw_key}"
    )


def _dispatch_first_worker_step(task: ScrivenerTask) -> None:
    index = call_index.for_data_key(task.data_key)
    step_key = call_index.first_step_key(index)

    if step_key is None:
        raise OrchestratorContractError(
            f"call index has no worker steps; cannot export final result: {index.redis_key}"
        )

    _post_worker_step(
        step_key=step_key,
        data_key=call_index.call_key(index),
    )


def _advance_after_step_write(result_key: str) -> None:
    index = call_index.for_data_key(result_key)
    result = RedisKey(result_key)
    step_number = call_index.slot_for_key(index, result_key)

    if result.kind == "failure":
        _post_scrivener_call_failed(result_key)
        return

    next_step = call_index.next_step_key_after(index, step_number)
    if next_step is None:
        _post_scrivener_call_completed(result_key)
        return

    _post_worker_step(
        step_key=next_step,
        data_key=call_index.latest_data_key(index),
    )


def _post_worker_step(*, step_key: str, data_key: str) -> None:
    task = make_worker_step(step_key=step_key, data_key=data_key)
    task.save()
    worker_inbox.post(str(task.redis_key))


def _post_scrivener_call_completed(result_key: str) -> None:
    task = make_scrivener_call_completed(data_key=result_key)
    task.save()
    scrivener_inbox.post(str(task.redis_key))


def _post_scrivener_call_failed(result_key: str) -> None:
    task = make_scrivener_call_failed(data_key=result_key)
    task.save()
    scrivener_inbox.post(str(task.redis_key))


__all__ = ["handle_done"]
