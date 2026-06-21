"""Handle a newly posted cursor key.

The enqueuer owns creation of the cursor and results index.  The orchestrator
observes the cursor post and sends the first ledger task to scrivener.
"""

from __future__ import annotations

from asc.models.process.cursor import Cursor
from asc.scrivener import inbox as scrivener_inbox

from ..keys import RuntimeKey
from ..tasks import make_scrivener_write_call


def handle(posted: RuntimeKey) -> None:
    cursor = Cursor.load(f"cursor:{posted.identity}:index")
    task = make_scrivener_write_call(cursor)
    task.save()
    scrivener_inbox.post(str(task.redis_key))


__all__ = ["handle"]
