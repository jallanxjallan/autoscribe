from __future__ import annotations

from asc.ledger.connect import LedgerConnection
from asc.orchestrator.errors import OrchestratorContractError
from asc.orchestrator.outcome import handle_worker_outcome
from asc.orchestrator.pending import handle_pending_signal
from asc.orchestrator.signals import ORCHESTRATOR_PENDING, WORKER_OUTCOME


def handle_orchestrator_signal(
    *,
    ledger: LedgerConnection,
    cursor_key: str,
    source: str = ORCHESTRATOR_PENDING,
) -> str:
    """Receive a cursor signal and hand it to the appropriate handler."""
    if source == ORCHESTRATOR_PENDING:
        return handle_pending_signal(cursor_key=cursor_key)

    if source == WORKER_OUTCOME:
        return handle_worker_outcome(ledger=ledger, cursor_key=cursor_key)

    raise OrchestratorContractError(f"unknown orchestrator signal source: {source!r}")


__all__ = ["handle_orchestrator_signal"]
