"""Handle daemon outcomes.

Outcome is only a task-completion signal. It does not carry copied task
metadata. The orchestrator reloads the original task by Outcome.identity and
uses the task plus the call index for routing context.
"""

from typing import Any

from asc.models.process.task import Outcome, ScrivenerTask, WorkerTask
from asc.redis.key import RedisKey
from asc.redis.primitives import hashes
from asc.scrivener import inbox as scrivener_inbox
from asc.scrivener.maps import CALLS_TABLE
from asc.worker import inbox as worker_inbox

from ..contracts import (
    SCRIVENER_CALL_COMPLETED,
    SCRIVENER_CALL_FAILED,
    SCRIVENER_WRITE_CALL,
    SCRIVENER_WRITE_STEP,
    WORKER_EXECUTE_STEP,
)
from ..errors import OrchestratorContractError
from ..tasks import make_scrivener_call_completed, make_scrivener_call_failed, make_worker_step
from ._runtime import (
    call_index_for_data_key,
    call_key_for_index,
    first_step_key,
    latest_data_key,
    next_step_key_after,
    required_text,
    set_result_slot,
    slot_for_key,
)

SCRIVENER_PACKAGE = "scrivener"
WORKER_PACKAGE = "worker"
SUCCESS = "success"
FAILURE = "failure"
TASK = "task"


def handle(key: RedisKey) -> None:
    outcome = Outcome.load(str(key))
    task = _load_task_for_outcome(outcome)

    if isinstance(task, ScrivenerTask):
        _handle_scrivener(outcome=outcome, task=task)
        return

    if isinstance(task, WorkerTask):
        _handle_worker(outcome=outcome, task=task)
        return

    raise OrchestratorContractError(
        f"unknown task type for outcome {outcome.raw_key}: {type(task).__name__}"
    )


def _load_task_for_outcome(outcome: Outcome) -> ScrivenerTask | WorkerTask:
    task_key = RedisKey(kind=TASK, identity=outcome.identity)
    raw = hashes.hgetall(task_key)
    if not raw:
        raise OrchestratorContractError(f"missing task for outcome: {task_key.raw_key}")

    package = required_text(raw.get("package"), "task.package")
    if package == SCRIVENER_PACKAGE:
        return ScrivenerTask.model_validate(raw)
    if package == WORKER_PACKAGE:
        return WorkerTask.model_validate(raw)

    raise OrchestratorContractError(
        f"unknown task package {package!r} for outcome: {task_key.raw_key}"
    )


def _handle_scrivener(*, outcome: Outcome, task: ScrivenerTask) -> None:
    result = required_text(outcome.result, "outcome.result")
    if result == FAILURE:
        # There is no safe next route for a failed ledger operation.
        return

    if result != SUCCESS:
        raise OrchestratorContractError(
            f"unknown scrivener outcome result {result!r}: {outcome.raw_key}"
        )

    if task.action == SCRIVENER_WRITE_CALL:
        _dispatch_first_worker_step(task)
        return

    if task.action == SCRIVENER_WRITE_STEP:
        # Worker outcomes own step progression. A scrivener write_step outcome is
        # an acknowledgement, not a route trigger.
        return

    if task.action in {SCRIVENER_CALL_COMPLETED, SCRIVENER_CALL_FAILED}:
        return

    raise OrchestratorContractError(
        f"unknown scrivener task action {task.action!r}: {task.raw_key}"
    )


def _dispatch_first_worker_step(task: ScrivenerTask) -> None:
    call_index = call_index_for_data_key(task.data_key)
    step_key = first_step_key(call_index)

    if step_key is None:
        _post_scrivener_call_completed(call_index)
        return

    _post_worker_step(
        step_key=step_key,
        data_key=call_key_for_index(call_index),
    )


def _handle_worker(*, outcome: Outcome, task: WorkerTask) -> None:
    if task.action != WORKER_EXECUTE_STEP:
        raise OrchestratorContractError(
            f"unknown worker task action {task.action!r}: {task.raw_key}"
        )

    result = required_text(outcome.result, "outcome.result")
    if result == SUCCESS:
        _handle_worker_success(outcome=outcome, task=task)
        return

    if result == FAILURE:
        _handle_worker_failure(outcome=outcome, task=task)
        return

    raise OrchestratorContractError(
        f"unknown worker outcome result {result!r}: {outcome.raw_key}"
    )


def _handle_worker_success(*, outcome: Outcome, task: WorkerTask) -> None:
    call_index = call_index_for_data_key(task.data_key)
    step_number = slot_for_key(call_index, task.step_key)
    output_key = required_text(outcome.output_key, "outcome.output_key")

    set_result_slot(call_index, step_number=step_number, result_key=output_key)

    next_step = next_step_key_after(call_index, step_number)
    if next_step is None:
        _post_scrivener_call_completed(call_index)
        return

    _post_worker_step(
        step_key=next_step,
        data_key=latest_data_key(call_index),
    )


def _handle_worker_failure(*, outcome: Outcome, task: WorkerTask) -> None:
    call_index = call_index_for_data_key(task.data_key)
    step_number = slot_for_key(call_index, task.step_key)
    output_key = required_text(outcome.output_key, "outcome.output_key")

    set_result_slot(call_index, step_number=step_number, result_key=output_key)
    _post_scrivener_call_failed(call_index)


def _post_worker_step(*, step_key: str, data_key: str) -> None:
    task = make_worker_step(step_key=step_key, data_key=data_key)
    task.save()
    worker_inbox.post(str(task.redis_key))


def _post_scrivener_call_completed(call_index: Any) -> None:
    task = make_scrivener_call_completed(
        table=CALLS_TABLE,
        data_key=call_key_for_index(call_index),
    )
    task.save()
    scrivener_inbox.post(str(task.redis_key))


def _post_scrivener_call_failed(call_index: Any) -> None:
    task = make_scrivener_call_failed(
        table=CALLS_TABLE,
        data_key=call_key_for_index(call_index),
    )
    task.save()
    scrivener_inbox.post(str(task.redis_key))


__all__ = ["handle"]
