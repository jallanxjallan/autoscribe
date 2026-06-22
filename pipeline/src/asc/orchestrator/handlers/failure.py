"""Handle a worker failure notice.

A failure notice is ``failure:<worker_task_identity>``. The orchestrator opens
the worker task for processing-chain context, records the failure key in the
results index, then asks scrivener to commit the terminal failure.
"""

import json

from asc.models.process.cursor import Cursor
from asc.models.process.result import Failure
from asc.models.process.task import WorkerTask
from asc.scrivener import inbox as scrivener_inbox
from asc.state.results import ResultsIndex

from ..tasks import make_scrivener_call_failed


def handle(identity: str) -> None:
    task = WorkerTask.load(WorkerTask.key_for_identity(identity))
    cursor = Cursor.load(task.cursor_key)
    failure_key = _failure_key(task)

    ResultsIndex.from_identity(cursor.identity).replace_step_key(
        task.step_number,
        expected_key=str(task.redis_key),
        replacement_key=failure_key,
    )

    scrivener_task = make_scrivener_call_failed(
        cursor=cursor,
        failure_key=failure_key,
        failed_at_step=task.step_number,
        failure=Failure.load(failure_key),
    )
    scrivener_task.save()
    scrivener_inbox.post(str(scrivener_task.redis_key))


def _failure_key(task: WorkerTask) -> str:
    try:
        args = json.loads(task.args_json or "{}")
    except json.JSONDecodeError:
        args = {}
    key = args.get("failure_key")
    if key:
        return str(key)
    return str(Failure.key_for_identity(task.identity))


__all__ = ["handle"]
