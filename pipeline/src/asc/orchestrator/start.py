from __future__ import annotations

from asc.ledger.connect import LedgerConnection
from asc.ledger.records.call import insert_call_record_with_connection
from asc.orchestrator.queues import enqueue_worker
from asc.orchestrator.state import mark_started, save_call_state
from asc.orchestrator.verify import verify_input_artifact


def handle_call_start(*, conn: LedgerConnection, call_state, call_state_key: str) -> str:
    """Ledger a materialized call_state and stage it for worker execution."""

    verify_input_artifact(call_state)
    insert_call_record_with_connection(conn=conn, call=call_state, commit=False)
    mark_started(call_state)
    save_call_state(call_state)
    enqueue_worker(call_state_key)
    return call_state_key


__all__ = ["handle_call_start"]
