"""Handle a worker-produced response key.

The worker owns writing the response object and inserting that key into the
assigned results-index slot.  The orchestrator only verifies that the posted key
is the canonical results-index entry for the step, then asks scrivener to commit
it to the ledger.
"""

from __future__ import annotations

from ..context import OrchestratorContext
from ..errors import OrchestratorContractError
from ..keys import RuntimeKey, response_step_number
from ..tasks import make_scrivener_write_step, task_key


def handle(posted: RuntimeKey, context: OrchestratorContext) -> None:
    step_number = response_step_number(posted)
    expected = context.store.result_key_for_step(
        identity=posted.identity,
        step_number=step_number,
    )
    if expected != posted.raw:
        raise OrchestratorContractError(
            f"posted response is not canonical for step {step_number}: "
            f"posted={posted.raw!r} results_index={expected!r}"
        )

    cursor = context.store.load_cursor_for_identity(posted.identity)
    task = make_scrivener_write_step(
        cursor=cursor,
        response_key=posted.raw,
        step_number=step_number,
    )
    key = context.store.save_task(task)
    context.scrivener_inbox.post(key or task_key(task))


__all__ = ["handle"]
