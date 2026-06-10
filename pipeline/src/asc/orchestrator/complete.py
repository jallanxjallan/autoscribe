from __future__ import annotations

from typing import Any

from asc.ledger.connect import LedgerConnection

from asc.orchestrator.state import mark_completed, save_call_state
from asc.orchestrator.verify import verify_output_artifact


def handle_complete(*, conn: LedgerConnection, call_state: Any) -> None:
    """Persist terminal success after verifying the terminal artifact."""

    terminal_content_key = verify_output_artifact(call_state)
    _insert_result_record(conn=conn, call_state=call_state, terminal_content_key=terminal_content_key)
    mark_completed(call_state)
    save_call_state(call_state)


def _insert_result_record(
    *, conn: LedgerConnection, call_state: Any, terminal_content_key: str
) -> None:
    try:
        from asc.ledger.records.result import insert_result_record_with_connection
    except ModuleNotFoundError:
        return

    try:
        insert_result_record_with_connection(
            conn=conn,
            call_state=call_state,
            terminal_content_key=terminal_content_key,
            commit=False,
        )
        return
    except TypeError:
        pass

    # Compatibility: older ledgers accept `result`, not call_state.  If the
    # call_state exposes a final result/report object, pass it through.
    for name in ("result", "worker_report", "last_report"):
        value = getattr(call_state, name, None)
        if value is not None:
            insert_result_record_with_connection(
                conn=conn,
                result=value,
                terminal_step_id=getattr(call_state, "terminal_step_id", None),
                commit=False,
            )
            return
