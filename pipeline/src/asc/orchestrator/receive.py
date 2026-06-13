from __future__ import annotations

from asc.ledger.connect import LedgerConnection
from asc.models.runtime.cursor import RuntimeCursor
from asc.orchestrator.errors import OrchestratorContractError
from asc.orchestrator.queues import enqueue_worker, mark_complete, touch_active


def handle_orchestrator_signal(
    *,
    ledger: LedgerConnection,
    cursor_key: str,
    source: str = "orchestrator_pending",
) -> str:
    # cursor = RuntimeCursor.load(cursor_key)

    # pending signal means: send this cursor to worker queue
    if source == "orchestrator_pending":
        enqueue_worker(cursor_key)
        touch_active(cursor_key)
        return "queued-worker"

    # outcome signal means: worker returned cursor; inspect output artifact/result
    if source == "worker_outcome":
        # success/failure should come from output existence / result record,
        # not cursor.status
        mark_complete(cursor_key)
        return "received-outcome"

    raise OrchestratorContractError(f"unknown orchestrator signal source: {source!r}")