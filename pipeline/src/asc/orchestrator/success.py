from __future__ import annotations

from asc.ledger.connect import LedgerConnection

from asc.orchestrator.receive import handle_worker_response


def handle_success(*, conn: LedgerConnection, call_state_key: str, **_: object) -> str:
    """Compatibility wrapper for old imports.

    Success is no longer derived from StepResultRecord.  The caller must pass a
    call_state key so the orchestrator can verify the artifact.
    """

    return handle_worker_response(conn=conn, call_state_key=call_state_key)
