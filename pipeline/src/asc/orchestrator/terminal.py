from __future__ import annotations

from asc.ledger.connect import LedgerConnection
from asc.orchestrator.queues import bump_terminal_cursor


def record_terminal_result(*, ledger: LedgerConnection, cursor_key: str) -> None:
    """Persist the terminal result row.

    Current package snapshots do not expose the final ledger API. Keep this call
    isolated so the real result-row insert can be wired here without changing
    daemon, queue, or outcome code.
    """
    _ = ledger
    _ = cursor_key


def close_terminal_cursor(*, ledger: LedgerConnection, cursor_key: str) -> str:
    """Record terminal state and move the cursor out of active rotation."""
    # Future production note:
    # inspect the worker result/failure here, write the ledger row, and let
    # orchestrator policy decide retries/failure handling.
    record_terminal_result(ledger=ledger, cursor_key=cursor_key)
    bump_terminal_cursor(cursor_key)
    return "terminal-recorded"


__all__ = [
    "close_terminal_cursor",
    "record_terminal_result",
]
