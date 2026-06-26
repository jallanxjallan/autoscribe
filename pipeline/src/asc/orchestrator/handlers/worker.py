"""Decisions after worker tasks complete."""

from asc.models.process.task import Outcome, WorkerTask
from asc.redis.key import RedisKey
from asc.scrivener import inbox as scrivener_inbox

from ..contracts import WORKER_EXECUTE_STEP
from ..errors import OrchestratorContractError
from ..tasks import make_scrivener_write_step
from . import call_index

SUCCESS = "success"
FAILURE = "failure"
SUCCESS_RESULT_KINDS = {"response", "transform", "retrieval"}
FAILURE_RESULT_KIND = "failure"


def handle_done(*, task: WorkerTask, outcome: Outcome) -> None:
    if task.action != WORKER_EXECUTE_STEP:
        raise OrchestratorContractError(
            f"unknown worker task action {task.action!r}: {task.raw_key}"
        )

    status = call_index.required_text(outcome.status, "outcome.status")
    if status in {SUCCESS, FAILURE}:
        _record_worker_result(task=task, outcome=outcome, status=status)
        return

    raise OrchestratorContractError(
        f"unknown worker outcome status {status!r}: {outcome.raw_key}"
    )


def _record_worker_result(*, task: WorkerTask, outcome: Outcome, status: str) -> None:
    index = call_index.for_data_key(task.data_key)
    step_number = call_index.slot_for_key(index, task.step_key)
    result_key = call_index.required_text(outcome.message, "outcome.message")
    _validate_worker_result_key(status=status, result_key=result_key)

    call_index.set_result_slot(index, step_number=step_number, result_key=result_key)
    _post_scrivener_write_step(data_key=result_key)


def _validate_worker_result_key(*, status: str, result_key: str) -> None:
    result = RedisKey(result_key)
    if status == SUCCESS and result.kind not in SUCCESS_RESULT_KINDS:
        raise OrchestratorContractError(
            "worker success outcome linked non-success result key: "
            f"status={status!r} result_key={result.raw_key!r}"
        )
    if status == FAILURE and result.kind != FAILURE_RESULT_KIND:
        raise OrchestratorContractError(
            "worker failure outcome linked non-failure result key: "
            f"status={status!r} result_key={result.raw_key!r}"
        )


def _post_scrivener_write_step(*, data_key: str) -> None:
    task = make_scrivener_write_step(data_key=data_key)
    task.save()
    scrivener_inbox.post(str(task.redis_key))


__all__ = ["handle_done"]
