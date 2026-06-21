"""Handle a posted failure key.

A worker failure is still a results-index fact.  The worker writes the failure
object into the assigned slot and posts the failure key.  The orchestrator
verifies that the key is canonical for the step, loads the failure payload, and
then applies failure policy.

Failure policy is deliberately boring for this draft: no retry yet.  The
orchestrator tasks scrivener to record the stopped call.  A later policy module
can decide retry vs terminal failure without changing the inbox contract.
"""

from __future__ import annotations

from ..context import OrchestratorContext
from ..errors import OrchestratorContractError
from ..keys import RuntimeKey, response_step_number
from ..tasks import make_scrivener_call_failed, task_key


def handle(posted: RuntimeKey, context: OrchestratorContext) -> None:
    step_number = response_step_number(posted)
    expected = context.store.result_key_for_step(
        identity=posted.identity,
        step_number=step_number,
    )
    if expected != posted.raw:
        raise OrchestratorContractError(
            f"posted failure is not canonical for step {step_number}: "
            f"posted={posted.raw!r} results_index={expected!r}"
        )

    failure = context.store.load_failure(posted.raw)
    cursor = context.store.load_cursor_for_identity(posted.identity)

    task = make_scrivener_call_failed(
        cursor=cursor,
        failure_key=posted.raw,
        failed_at_step=step_number,
        failure=failure,
    )
    key = context.store.save_task(task)
    context.scrivener_inbox.post(key or task_key(task))


__all__ = ["handle"]
