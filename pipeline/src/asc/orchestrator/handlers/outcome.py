"""Handle daemon outcomes.

Outcome is the only daemon-completion message the orchestrator accepts. Concrete
artifacts remain behind their own keys:

* worker success: result_key -> response/transform/retrieval key
* worker failure: failure_key -> failure key
* scrivener success: the ledger write has already happened
* scrivener failure: failure_key -> failure key
"""

from asc.models.process.task import Outcome
from asc.redis.key import RedisKey
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
    next_step_key_after,
    required_int,
    required_text,
    set_result_slot,
)

SCRIVENER_PACKAGE = "scrivener"
WORKER_PACKAGE = "worker"
SUCCESS = "success"
FAILURE = "failure"


def handle(key: RedisKey) -> None:
    outcome = Outcome.load(str(key))

    if outcome.package == SCRIVENER_PACKAGE:
        _handle_scrivener(outcome)
        return

    if outcome.package == WORKER_PACKAGE:
        _handle_worker(outcome)
        return

    raise OrchestratorContractError(
        f"unknown outcome package {outcome.package!r}: {outcome.raw_key}"
    )


def _handle_scrivener(outcome: Outcome) -> None:
    if outcome.status == FAILURE:
        # Scrivener has already written the failure artifact. There is no safe
        # next route for a failed ledger write.
        return

    if outcome.status != SUCCESS:
        raise OrchestratorContractError(
            f"unknown scrivener outcome status {outcome.status!r}: {outcome.raw_key}"
        )

    if outcome.action == SCRIVENER_WRITE_CALL:
        _dispatch_first_worker_step(outcome)
        return

    if outcome.action == SCRIVENER_WRITE_STEP:
        # Worker outcomes own step progression. A scrivener write_step outcome is
        # an acknowledgement, not a route trigger.
        return

    if outcome.action in {SCRIVENER_CALL_COMPLETED, SCRIVENER_CALL_FAILED}:
        return

    raise OrchestratorContractError(
        f"unknown scrivener outcome action {outcome.action!r}: {outcome.raw_key}"
    )


def _dispatch_first_worker_step(outcome: Outcome) -> None:
    data_key = required_text(outcome.data_key, "outcome.data_key")
    call_index = call_index_for_data_key(data_key)
    step_key = first_step_key(call_index)

    if step_key is None:
        _post_scrivener_call_completed(call_index)
        return

    task = make_worker_step(
        step_key=step_key,
        data_key=call_key_for_index(call_index),
    )
    task.save()
    worker_inbox.post(str(task.redis_key))


def _handle_worker(outcome: Outcome) -> None:
    if outcome.action != WORKER_EXECUTE_STEP:
        raise OrchestratorContractError(
            f"unknown worker outcome action {outcome.action!r}: {outcome.raw_key}"
        )

    if outcome.status == SUCCESS:
        _handle_worker_success(outcome)
        return

    if outcome.status == FAILURE:
        _handle_worker_failure(outcome)
        return

    raise OrchestratorContractError(
        f"unknown worker outcome status {outcome.status!r}: {outcome.raw_key}"
    )


def _handle_worker_success(outcome: Outcome) -> None:
    call_index = call_index_for_data_key(required_text(outcome.data_key, "outcome.data_key"))
    step_number = required_int(outcome.step_number, "outcome.step_number")
    result_key = required_text(outcome.result_key, "outcome.result_key")

    set_result_slot(call_index, step_number=step_number, result_key=result_key)

    next_step = next_step_key_after(call_index, step_number)
    if next_step is None:
        _post_scrivener_call_completed(call_index)
        return

    task = make_worker_step(
        step_key=next_step,
        data_key=call_key_for_index(call_index),
    )
    task.save()
    worker_inbox.post(str(task.redis_key))


def _handle_worker_failure(outcome: Outcome) -> None:
    call_index = call_index_for_data_key(required_text(outcome.data_key, "outcome.data_key"))
    step_number = required_int(outcome.step_number, "outcome.step_number")
    failure_key = required_text(outcome.failure_key, "outcome.failure_key")

    set_result_slot(call_index, step_number=step_number, result_key=failure_key)
    _post_scrivener_call_failed(call_index)


def _post_scrivener_call_completed(call_index) -> None:
    task = make_scrivener_call_completed(
        table=CALLS_TABLE,
        data_key=call_key_for_index(call_index),
    )
    task.save()
    scrivener_inbox.post(str(task.redis_key))


def _post_scrivener_call_failed(call_index) -> None:
    task = make_scrivener_call_failed(
        table=CALLS_TABLE,
        data_key=call_key_for_index(call_index),
    )
    task.save()
    scrivener_inbox.post(str(task.redis_key))


__all__ = ["handle"]
