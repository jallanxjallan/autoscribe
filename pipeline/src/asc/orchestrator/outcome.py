from __future__ import annotations

from asc.ledger.connect import LedgerConnection
from asc.orchestrator.queues import enqueue_worker, touch_active_cursor
from asc.orchestrator.state import advance_cursor, is_terminal_cursor, load_cursor
from asc.orchestrator.terminal import close_terminal_cursor


def handle_worker_outcome(*, ledger: LedgerConnection, cursor_key: str) -> str:
    """Handle a worker completion signal.

    The fixed response index is the source of truth. If all slots are filled,
    the call is terminal. Otherwise the next empty slot becomes current_step and
    is handed to a worker.
    """
    cursor = load_cursor(cursor_key)
    touch_active_cursor(cursor_key)

    if is_terminal_cursor(cursor):
        return close_terminal_cursor(ledger=ledger, cursor_key=cursor_key)

    cursor = advance_cursor(cursor)
    enqueue_worker(cursor_key)
    return f"queued-step-{cursor.current_step}"


__all__ = ["handle_worker_outcome"]
