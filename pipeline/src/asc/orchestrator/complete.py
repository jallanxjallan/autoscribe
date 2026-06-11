from __future__ import annotations

from asc.ledger.connect import LedgerConnection
from asc.ledger.records.result import insert_result_record_with_connection
from asc.models.runtime.result import StepResultRecord
from asc.orchestrator.state import mark_completed, save_call_state


def handle_complete(
    *,
    conn: LedgerConnection,
    call_state,
    result: StepResultRecord,
    terminal_step_id: int,
) -> None:
    """Persist the terminal result pointer for a successful final step."""

    insert_result_record_with_connection(
        conn=conn,
        result=result,
        terminal_step_id=terminal_step_id,
        commit=False,
    )
    mark_completed(call_state)
    save_call_state(call_state)
