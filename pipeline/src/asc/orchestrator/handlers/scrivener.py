"""Decisions after scrivener tasks complete."""

from asc.models.process.task import Outcome, ScrivenerTask
from asc.scrivener import inbox as scrivener_inbox
from asc.scrivener.maps import CALLS_TABLE
from asc.worker import inbox as worker_inbox

from ..contracts import (
    SCRIVENER_CALL_COMPLETED,
    SCRIVENER_CALL_FAILED,
    SCRIVENER_WRITE_CALL,
    SCRIVENER_WRITE_STEP,
)
from ..errors import OrchestratorContractError
from ..tasks import make_scrivener_call_completed, make_worker_step
from . import call_index

SUCCESS = "success"
FAILURE = "failure"


def handle_done(*, task: ScrivenerTask, outcome: Outcome) -> None:
    status = call_index.required_text(outcome.status, "outcome.status")
    if status == FAILURE:
        # A failed ledger write has no safe continuation.
        return

    if status != SUCCESS:
        raise OrchestratorContractError(
            f"unknown scrivener outcome status {status!r}: {outcome.raw_key}"
        )

    if task.action == SCRIVENER_WRITE_CALL:
        _dispatch_first_worker_step(task)
        return

    if task.action == SCRIVENER_WRITE_STEP:
        # Worker completion drives step progression. A scrivener write_step
        # outcome is only a persistence acknowledgement.
        return

    if task.action in {SCRIVENER_CALL_COMPLETED, SCRIVENER_CALL_FAILED}:
        return

    raise OrchestratorContractError(
        f"unknown scrivener task action {task.action!r}: {task.raw_key}"
    )


def _dispatch_first_worker_step(task: ScrivenerTask) -> None:
    index = call_index.for_data_key(task.data_key)
    step_key = call_index.first_step_key(index)

    if step_key is None:
        _post_scrivener_call_completed(index)
        return

    _post_worker_step(
        step_key=step_key,
        data_key=call_index.call_key(index),
    )


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


__all__ = ["handle_done"]
