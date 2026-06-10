from __future__ import annotations

from typing import Any

from asc.ledger.connect import LedgerConnection

from asc.orchestrator.advance import advance_call_state
from asc.orchestrator.complete import handle_complete
from asc.orchestrator.failure import handle_failure
from asc.orchestrator.state import is_failed, load_call_state
from asc.orchestrator.verify import verify_output_artifact


def handle_worker_response(*, conn: LedgerConnection, call_state_key: str) -> str:
    """Process one worker-returned call_state key.

    Worker annotations are claims.  The orchestrator verifies the content
    artifact for the current step before advancing or completing the call.
    """

    call_state = load_call_state(call_state_key)

    if is_failed(call_state):
        handle_failure(conn=conn, call_state=call_state)
        return "failed"

    verify_output_artifact(call_state)
    if advance_call_state(call_state, call_state_key):
        return "advanced"

    handle_complete(conn=conn, call_state=call_state)
    return "complete"
