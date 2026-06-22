"""Handle task outcomes posted to the orchestrator inbox.

The inbox key kind is deliberately generic: ``outcome:<identity>``. Once the
outcome record is loaded, routing is based on the outcome fields:

    package  which package executed the task
    action   which task action completed
    result   success/failure

For the current smoke cycle, successful scrivener outcomes prove:
    orchestrator -> scrivener -> orchestrator

Worker dispatch remains parked here until the worker task executor is converted
to the new generic task shape.
"""

from asc.models.process.task import Outcome

from ..contracts import (
    SCRIVENER_CALL_COMPLETED,
    SCRIVENER_CALL_FAILED,
    SCRIVENER_WRITE_CALL,
    SCRIVENER_WRITE_STEP,
    WORKER_EXECUTE_STEP,
)
from ..errors import OrchestratorContractError


def handle(identity: str) -> None:
    outcome = Outcome.load(Outcome.key_for_identity(identity))

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


def _handle_scrivener_success(outcome: Outcome) -> None:
    if outcome.action == SCRIVENER_WRITE_CALL:
        # Smoke-test stop point. Later this should queue worker step 1.
        return

    if outcome.action == SCRIVENER_WRITE_STEP:
        # Later this should queue the next worker step or call_completed.
        return

    if outcome.action in {SCRIVENER_CALL_COMPLETED, SCRIVENER_CALL_FAILED}:
        return

    raise OrchestratorContractError(
        f"unknown scrivener outcome action {outcome.action!r}: {outcome.raw_key}"
    )


def _handle_worker_success(outcome: Outcome) -> None:
    if outcome.action == WORKER_EXECUTE_STEP:
        # Worker routing is deliberately parked for the current smoke cycle.
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


__all__ = ["handle"]
