from __future__ import annotations

from asc.ledger.connect import LedgerConnection
from asc.models.runtime.cursor import RuntimeCursor
from asc.orchestrator.errors import OrchestratorContractError
from asc.orchestrator.queues import (
    bump_terminal_cursor,
    enqueue_worker,
    touch_active_cursor,
)

ORCHESTRATOR_PENDING = "orchestrator_pending"
WORKER_OUTCOME = "worker_outcome"


def handle_orchestrator_signal(
    *,
    ledger: LedgerConnection,
    cursor_key: str,
    source: str = ORCHESTRATOR_PENDING,
) -> str:
    """Brain of the orchestrator.

    Queues only move cursor keys. This module owns cursor state transitions and
    ledger-facing orchestration decisions.
    """
    RuntimeCursor.load(cursor_key)
    touch_active_cursor(cursor_key)

    if source == ORCHESTRATOR_PENDING:
        enqueue_worker(cursor_key)
        return "queued-worker"

    if source == WORKER_OUTCOME:
        # The completion process is ledger-first: persist the terminal result row,
        # then bump the active cursor index far into the future for forensic
        # visibility. The actual result/failure inspection belongs here as the
        # step-result contract settles.
        _record_terminal_result(ledger=ledger, cursor_key=cursor_key)
        bump_terminal_cursor(cursor_key)
        return "terminal-recorded"

    raise OrchestratorContractError(f"unknown orchestrator signal source: {source!r}")


def _record_terminal_result(*, ledger: LedgerConnection, cursor_key: str) -> None:
    """Placeholder for terminal ledger write.

    Current package snapshots do not expose the final ledger API. Keep the call
    isolated so the real result-row insert can be wired here without changing
    daemon or queue code.
    """
    _ = ledger
    _ = cursor_key


__all__ = [
    "ORCHESTRATOR_PENDING",
    "WORKER_OUTCOME",
    "handle_orchestrator_signal",
]
