"""Legacy top-level orchestrator handler.

The public orchestrator inbox now accepts only call:<identity> and
outcome:<identity>. This module is intentionally not imported by
orchestrator.handlers.HANDLERS. Keep it only as a short-term reference while
the old committed/response/failure/cursor message kinds are removed.
"""

"""Handle a scrivener committed notice.

A committed notice is ``committed:<task_identity>``. For this smoke cycle,
the identity points back to the generic scrivener Task that produced the
Outcome. Worker dispatch is deliberately parked after the committed notice is
handled.
"""

from asc.models.control.plan import Plan
from asc.models.process.cursor import Cursor
from asc.models.process.task import Task
from asc.orchestrator.contracts import (
    SCRIVENER_CALL_COMPLETED,
    SCRIVENER_CALL_FAILED,
    SCRIVENER_WRITE_CALL,
    SCRIVENER_WRITE_STEP,
)
from asc.scrivener import inbox as scrivener_inbox

from ..errors import OrchestratorContractError
from ..tasks import make_scrivener_call_completed, plan_step_count


def handle(identity: str) -> None:
    task = Task.load(Task.key_for_identity(identity))

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

    _dispatch_worker_step(cursor=cursor, plan=plan, step_number=1)


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

    _dispatch_worker_step(cursor=cursor, plan=plan, step_number=next_step)


def _dispatch_worker_step(*, cursor: Cursor, plan: Plan, step_number: int) -> None:
    """Worker dispatch is deliberately parked for the current smoke cycle.

    The temporary target is only:
        orchestrator -> scrivener -> orchestrator

    Once the generic worker task shape is wired back in, this function should
    create the next generic worker Task and post it to the worker inbox.
    """
    return None


__all__ = ["handle"]
