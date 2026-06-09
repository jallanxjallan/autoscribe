from __future__ import annotations

from asc.ledger.connect import LedgerConnection
from asc.ledger.records.result import insert_result_record_with_connection
from asc.ledger.records.step import insert_step_record_with_connection
from asc.ledger.util import model_value
from asc.models.runtime.result import StepResultRecord

from asc.orchestrator.routing import NextStepKeyLookup, StepQueueEnqueue


def handle_success(
    *,
    conn: LedgerConnection,
    result: StepResultRecord,
    next_step_key: NextStepKeyLookup,
    enqueue_step: StepQueueEnqueue,
) -> None:
    """Persist a successful step and route the pipeline forward.

    A missing next step key means the current successful response is terminal.
    Enqueue owns pre-creating step definitions; the orchestrator only advances
    to already-known step keys.
    """

    step_id = insert_step_record_with_connection(
        conn=conn,
        result=result,
        commit=False,
    )

    call_identity = str(model_value(result, "call_identity"))
    step_number = int(model_value(result, "step_number"))
    next_key = next_step_key(call_identity, step_number + 1)

    if next_key is not None:
        enqueue_step(next_key)
        return

    insert_result_record_with_connection(
        conn=conn,
        result=result,
        terminal_step_id=step_id,
        commit=False,
    )
