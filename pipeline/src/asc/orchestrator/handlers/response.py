"""Handle a worker-produced response key.

The worker owns writing the response object and inserting that key into the
assigned results-index slot.  The orchestrator verifies the canonical
results-index entry for the step, then asks scrivener to commit it to the ledger.
"""


from asc.models.process.cursor import Cursor
from asc.scrivener import inbox as scrivener_inbox
from asc.state.results import ResultsIndex

from ..errors import OrchestratorContractError
from ..keys import RuntimeKey, response_step_number
from ..tasks import make_scrivener_write_step


def handle(posted: RuntimeKey) -> None:
    step_number = response_step_number(posted)
    expected = str(ResultsIndex(f"results:{posted.identity}:index").get(step_number))
    if expected != posted.raw:
        raise OrchestratorContractError(
            f"posted response is not canonical for step {step_number}: "
            f"posted={posted.raw!r} results_index={expected!r}"
        )

    cursor = Cursor.load(f"cursor:{posted.identity}:index")
    task = make_scrivener_write_step(
        cursor=cursor,
        response_key=posted.raw,
        step_number=step_number,
    )
    task.save()
    scrivener_inbox.post(str(task.key))


__all__ = ["handle"]
