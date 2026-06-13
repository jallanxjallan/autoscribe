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
    cursor = RuntimeCursor.load(cursor_key)

    if cursor.status == "pending":
        cursor.status = "queued"
        cursor.save()
        enqueue_worker(cursor_key)
        touch_active(cursor_key)
        return "queued-worker"

    if cursor.status == "success":
        cursor.status = "done"
        cursor.save()
        mark_complete(cursor_key)
        return "done"

    if cursor.status == "failed":
        mark_complete(cursor_key)
        return "failed"

    if cursor.status in {"queued", "working", "running"}:
        # Watchdog observation only. Do not enqueue or loop; just refresh the
        # active index so the next stale inspection is delayed.
        touch_active(cursor_key)
        return f"observed-{cursor.status}"

    if cursor.status == "done":
        mark_complete(cursor_key)
        return "already-done"

    raise OrchestratorContractError(f"unknown cursor status: {cursor.status!r}")
