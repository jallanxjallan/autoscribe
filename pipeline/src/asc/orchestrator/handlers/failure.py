"""Handle a posted failure key.

A worker failure is still a results-index fact.  The worker writes the failure
object into the assigned slot and posts the failure key.  The orchestrator
verifies that the key is canonical for the step, loads the failure payload, and
then applies failure policy.

Failure policy is deliberately boring for this draft: no retry yet.  The
orchestrator tasks scrivener to record the stopped call.  A later policy module
can decide retry vs terminal failure without changing the inbox contract.
"""


from asc.models.process.cursor import Cursor
from asc.models.process.result import Failure
from asc.scrivener import inbox as scrivener_inbox
from asc.state.results import ResultsIndex

from ..errors import OrchestratorContractError
from ..keys import RuntimeKey, response_step_number
from ..tasks import make_scrivener_call_failed


def handle(posted: RuntimeKey) -> None:
    step_number = response_step_number(posted)
    expected = str(ResultsIndex(f"results:{posted.identity}:index").get(step_number))
    if expected != posted.raw:
        raise OrchestratorContractError(
            f"posted failure is not canonical for step {step_number}: "
            f"posted={posted.raw!r} results_index={expected!r}"
        )

    cursor = Cursor.load(f"cursor:{posted.identity}:index")
    task = make_scrivener_call_failed(
        cursor=cursor,
        failure_key=posted.raw,
        failed_at_step=step_number,
        failure=Failure.load(posted.raw),
    )
    task.save()
    scrivener_inbox.post(str(task.key))


__all__ = ["handle"]
