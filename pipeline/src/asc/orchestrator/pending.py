from __future__ import annotations

from asc.models.runtime.cursor import RuntimeCursor
from asc.orchestrator.queues import enqueue_worker, touch_active_cursor


def handle_pending_signal(*, cursor_key: str) -> str:
    """Handle a newly pending runtime cursor.

    The pending signal means the orchestrator has accepted custody of the call
    and should hand the current cursor step to a worker.
    """
    RuntimeCursor.load(cursor_key)
    touch_active_cursor(cursor_key)
    enqueue_worker(cursor_key)
    return "queued-worker"


__all__ = ["handle_pending_signal"]
