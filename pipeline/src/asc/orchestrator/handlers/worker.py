"""Decisions after worker tasks complete."""

from asc.models.process.task import Outcome, WorkerTask
from asc.scrivener import inbox as scrivener_inbox
from asc.scrivener.maps import CALLS_TABLE
from asc.worker import inbox as worker_inbox

from ..contracts import WORKER_EXECUTE_STEP
from ..errors import OrchestratorContractError
from ..tasks import make_scrivener_call_completed, make_scrivener_call_failed, make_worker_step
from . import call_index

SUCCESS = "success"
FAILURE = "failure"


def handle_done(*, task: WorkerTask, outcome: Outcome) -> None:
    if task.action != WORKER_EXECUTE_STEP:
        raise OrchestratorContractError(
            f"unknown worker task action {task.action!r}: {task.raw_key}"
        )

    status = call_index.required_text(outcome.status, "outcome.status")
    if status == SUCCESS:
        _handle_success(task=task, outcome=outcome)
        return

    if status == FAILURE:
        _handle_failure(task=task, outcome=outcome)
        return

    raise OrchestratorContractError(
        f"unknown worker outcome status {status!r}: {outcome.raw_key}"
    )


def _handle_success(*, task: WorkerTask, outcome: Outcome) -> None:
    index = call_index.for_data_key(task.data_key)
    step_number = call_index.slot_for_key(index, task.step_key)
    result_key = call_index.required_text(outcome.message, "outcome.message")

    call_index.set_result_slot(index, step_number=step_number, result_key=result_key)

    next_step = call_index.next_step_key_after(index, step_number)
    if next_step is None:
        _post_scrivener_call_completed(index)
        return

    _post_worker_step(
        step_key=next_step,
        data_key=call_index.latest_data_key(index),
    )


def _handle_failure(*, task: WorkerTask, outcome: Outcome) -> None:
    index = call_index.for_data_key(task.data_key)
    step_number = call_index.slot_for_key(index, task.step_key)
    result_key = call_index.required_text(outcome.message, "outcome.message")

    call_index.set_result_slot(index, step_number=step_number, result_key=result_key)
    _post_scrivener_call_failed(index)


def _post_worker_step(*, step_key: str, data_key: str) -> None:
    task = make_worker_step(step_key=step_key, data_key=data_key)
    task.save()
    worker_inbox.post(str(task.redis_key))


def _post_scrivener_call_completed(index: object) -> None:
    task = make_scrivener_call_completed(
        table=CALLS_TABLE,
        data_key=call_index.call_key(index),
    )
    task.save()
    scrivener_inbox.post(str(task.redis_key))


def _post_scrivener_call_failed(index: object) -> None:
    task = make_scrivener_call_failed(
        table=CALLS_TABLE,
        data_key=call_index.call_key(index),
    )
    task.save()
    scrivener_inbox.post(str(task.redis_key))


__all__ = ["handle_done"]
