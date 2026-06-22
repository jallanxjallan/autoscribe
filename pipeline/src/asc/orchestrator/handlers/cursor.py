"""Handle a newly posted cursor notice.

The enqueuer owns creation of the cursor and results index. The orchestrator
receives a ``cursor:<identity>`` notice, loads the cursor record, and sends the
first ledger task to scrivener.
"""


from asc.models.process.cursor import Cursor
from asc.scrivener import inbox as scrivener_inbox

from ..tasks import make_scrivener_write_call


def handle(identity: str) -> None:
    cursor = Cursor.load(Cursor.key_for_identity(identity))
    task = make_scrivener_write_call(cursor)
    task.save()
    scrivener_inbox.post(str(task.redis_key))


__all__ = ["handle"]
