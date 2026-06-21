"""Handle a scrivener committed key.

Scrivener owns the ledger write.  The orchestrator treats a committed key as a
fact that the ledger accepted something, then routes the next worker or terminal
scrivener task.
"""

from __future__ import annotations

from ..contracts import COMMITTED_CALL_SUFFIX, COMMITTED_COMPLETED_SUFFIX, COMMITTED_FAILED_SUFFIX
from ..context import OrchestratorContext
from ..errors import OrchestratorContractError
from ..keys import RuntimeKey, committed_step_number
from ..tasks import (
    make_scrivener_call_completed,
    make_worker_step,
    plan_step_count,
    task_key,
)


def handle(posted: RuntimeKey, context: OrchestratorContext) -> None:
    suffix = posted.require_suffix()

    if suffix in {COMMITTED_COMPLETED_SUFFIX, COMMITTED_FAILED_SUFFIX}:
        return

    cursor = context.store.load_cursor_for_identity(posted.identity)

    if suffix == COMMITTED_CALL_SUFFIX:
        plan = context.store.load_plan(cursor.plan_key)
        total_steps = plan_step_count(plan)
        _after_call_committed(context=context, cursor=cursor, plan=plan, total_steps=total_steps)
        return

    step_number = committed_step_number(posted)
    plan = context.store.load_plan(cursor.plan_key)
    total_steps = plan_step_count(plan)
    _after_step_committed(
        context=context,
        cursor=cursor,
        plan=plan,
        total_steps=total_steps,
        step_number=step_number,
    )


def _after_call_committed(*, context: OrchestratorContext, cursor: object, plan: object, total_steps: int) -> None:
    if total_steps < 1:
        task = make_scrivener_call_completed(cursor=cursor, completed_after_step=0)
        key = context.store.save_task(task)
        context.scrivener_inbox.post(key or task_key(task))
        return

    task = make_worker_step(
        cursor=cursor,
        plan=plan,
        step_number=1,
        input_key=context.store.input_key_for_step(identity=cursor.identity, step_number=1),
    )
    key = context.store.save_task(task)
    context.worker_inbox.post(key or task_key(task))


def _after_step_committed(
    *,
    context: OrchestratorContext,
    cursor: object,
    plan: object,
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
        key = context.store.save_task(task)
        context.scrivener_inbox.post(key or task_key(task))
        return

    task = make_worker_step(
        cursor=cursor,
        plan=plan,
        step_number=next_step,
        input_key=context.store.input_key_for_step(identity=cursor.identity, step_number=next_step),
    )
    key = context.store.save_task(task)
    context.worker_inbox.post(key or task_key(task))


__all__ = ["handle"]
