"""Handle a worker failure notice.

A failure notice is ``failure:<worker_task_identity>``. Failure is the one worker
notice where the orchestrator opens the produced record, because failure policy
needs to know what happened. Processing-chain context still comes from the
worker task, not from the failure payload or the notice key.
"""


from asc.models.process.cursor import Cursor
from asc.models.process.result import Failure
from asc.models.process.task import WorkerTask
from asc.scrivener import inbox as scrivener_inbox

from ..tasks import make_scrivener_call_failed


def handle(identity: str) -> None:
    task = WorkerTask.load(WorkerTask.key_for_identity(identity))
    cursor = Cursor.load(task.cursor_key)
    failure_key = str(Failure.key_for_identity(identity))

    scrivener_task = make_scrivener_call_failed(
        cursor=cursor,
        failure_key=failure_key,
        failed_at_step=task.step_number,
        failure=Failure.load(failure_key),
    )
    scrivener_task.save()
    scrivener_inbox.post(str(scrivener_task.redis_key))


__all__ = ["handle"]
