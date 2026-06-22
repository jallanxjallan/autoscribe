"""Handle a scrivener committed notice.

A committed notice is ``committed:<scrivener_task_identity>``. The notice key is
not opened as a record. Its identity points to the scrivener task that produced
the notice; the task carries the action, cursor, and step context.
"""


from asc.models.control.plan import Plan
from asc.models.process.cursor import Cursor
from asc.models.process.task import ScrivenerTask
from asc.orchestrator.contracts import (
    SCRIVENER_CALL_COMPLETED,
    SCRIVENER_CALL_FAILED,
    SCRIVENER_WRITE_CALL,
    SCRIVENER_WRITE_STEP,
)
from asc.scrivener import inbox as scrivener_inbox
from asc.state.results import ResultsIndex
from asc.worker import inbox as worker_inbox

from ..errors import OrchestratorContractError
from ..tasks import (
    make_scrivener_call_completed,
    make_worker_step,
    plan_step_count,
)


def handle(identity: str) -> None:
    task = ScrivenerTask.load(ScrivenerTask.key_for_identity(identity))

    if task.action in {SCRIVENER_CALL_COMPLETED, SCRIVENER_CALL_FAILED}:
        return

    cursor = Cursor.load(task.cursor_key)
    plan = Plan.load(cursor.plan_key)

    if task.action == SCRIVENER_WRITE_CALL:
        _after_call_committed(cursor=cursor, plan=plan, total_steps=plan_step_count(plan))
        return

    if task.action == SCRIVENER_WRITE_STEP:
        _after_step_committed(
            cursor=cursor,
            plan=plan,
            total_steps=plan_step_count(plan),
            step_number=task.task_number,
        )
        return

    raise OrchestratorContractError(
        f"unknown scrivener task action {task.action!r}: {task.redis_key}"
    )


def _after_call_committed(*, cursor: Cursor, plan: Plan, total_steps: int) -> None:
    if total_steps < 1:
        task = make_scrivener_call_completed(cursor=cursor, completed_after_step=0)
        task.save()
        scrivener_inbox.post(str(task.redis_key))
        return

    task = make_worker_step(
        cursor=cursor,
        plan=plan,
        step_number=1,
        input_key=str(ResultsIndex(f"results:{cursor.identity}").input_key_for_step(1)),
    )
    task.save()
    worker_inbox.post(str(task.redis_key))


def _after_step_committed(
    *,
    cursor: Cursor,
    plan: Plan,
    total_steps: int,
    step_number: int,
) -> None:
    if step_number > total_steps:
        raise OrchestratorContractError(
            f"committed step {step_number} exceeds plan step count {total_steps}: {cursor.identity}"
        )

    next_step = step_number + 1
    if next_step > total_steps:
        task = make_scrivener_call_completed(cursor=cursor, completed_after_step=step_number)
        task.save()
        scrivener_inbox.post(str(task.redis_key))
        return

    task = make_worker_step(
        cursor=cursor,
        plan=plan,
        step_number=next_step,
        input_key=str(ResultsIndex(f"results:{cursor.identity}").input_key_for_step(next_step)),
    )
    task.save()
    worker_inbox.post(str(task.redis_key))


__all__ = ["handle"]
