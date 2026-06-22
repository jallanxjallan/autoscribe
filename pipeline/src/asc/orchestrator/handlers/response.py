"""Handle a worker response notice.

A response notice is ``response:<worker_task_identity>``. The orchestrator does
not open the response payload. It loads the worker task, which carries the
processing-chain context and the response output key, then asks scrivener to
commit that response.
"""


from asc.models.process.cursor import Cursor
from asc.models.process.task import WorkerTask
from asc.scrivener import inbox as scrivener_inbox

from ..tasks import make_scrivener_write_step


def handle(identity: str) -> None:
    task = WorkerTask.load(WorkerTask.key_for_identity(identity))
    cursor = Cursor.load(task.cursor_key)

    scrivener_task = make_scrivener_write_step(
        cursor=cursor,
        response_key=task.output_key,
        step_number=task.step_number,
    )
    scrivener_task.save()
    scrivener_inbox.post(str(scrivener_task.redis_key))


__all__ = ["handle"]
