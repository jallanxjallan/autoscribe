"""Handle a newly posted cursor key.

The enqueuer owns creation of the cursor, results index, and whatever active/index entry the enqueuer owns.
The orchestrator only observes the cursor post and sends the first ledger task to
scrivener.
"""

from __future__ import annotations

from ..context import OrchestratorContext
from ..keys import RuntimeKey
from ..tasks import make_scrivener_write_call, task_key


def handle(posted: RuntimeKey, context: OrchestratorContext) -> None:
    cursor = context.store.load_cursor_for_identity(posted.identity)
    task = make_scrivener_write_call(cursor)
    key = context.store.save_task(task)
    context.scrivener_inbox.post(key or task_key(task))


__all__ = ["handle"]
