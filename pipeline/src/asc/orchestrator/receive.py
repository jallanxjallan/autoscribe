from __future__ import annotations

from asc.ledger.connect import LedgerConnection

from asc.orchestrator.advance import advance_call_state
from asc.orchestrator.complete import handle_complete
from asc.orchestrator.outcome import handle_failure, handle_success
from asc.orchestrator.start import handle_call_start
from asc.orchestrator.state import is_failed, is_started, load_call_state


def handle_orchestrator_signal(*, conn: LedgerConnection, call_state_key: str) -> str:
    """Process one full call_state key from the single orchestrator queue.

    New calls and worker returns use the same queue. The mutable call_state
    status determines whether this signal starts a call, records a terminal
    worker failure, advances after worker success, or completes the call.
    """

    call_state = load_call_state(call_state_key)

    if not is_started(call_state):
        handle_call_start(conn=conn, call_state=call_state, call_state_key=call_state_key)
        return "started"

    if is_failed(call_state):
        handle_failure(conn=conn, call_state=call_state)
        return "failed"

    result, step_id = handle_success(conn=conn, call_state=call_state)
    if advance_call_state(call_state, call_state_key):
        return "advanced"

    handle_complete(
        conn=conn,
        call_state=call_state,
        result=result,
        terminal_step_id=step_id,
    )
    return "complete"


__all__ = ["handle_orchestrator_signal"]
