"""Handle a scrivener committed key.

Scrivener owns the ledger write.  The orchestrator treats a committed key as a
fact that the ledger accepted something, then routes the next worker or terminal
scrivener task.
"""


from asc.models.control.plan import Plan
from asc.models.process.cursor import Cursor
from asc.scrivener import inbox as scrivener_inbox
from asc.state.results import ResultsIndex
from asc.worker import inbox as worker_inbox

from ..contracts import COMMITTED_CALL_SUFFIX, COMMITTED_COMPLETED_SUFFIX, COMMITTED_FAILED_SUFFIX
from ..errors import OrchestratorContractError
from ..keys import RuntimeKey, committed_step_number
from ..tasks import (
    make_scrivener_call_completed,
    make_worker_step,
    plan_step_count,
)


def handle(posted: RuntimeKey) -> None:
    suffix = posted.require_suffix()

    if suffix in {COMMITTED_COMPLETED_SUFFIX, COMMITTED_FAILED_SUFFIX}:
        return

    cursor = Cursor.load(f"cursor:{posted.identity}:index")

    if suffix == COMMITTED_CALL_SUFFIX:
        plan = Plan.load(cursor.plan_key)
        _after_call_committed(cursor=cursor, plan=plan, total_steps=plan_step_count(plan))
        return

    step_number = committed_step_number(posted)
    plan = Plan.load(cursor.plan_key)
    _after_step_committed(
        cursor=cursor,
        plan=plan,
        total_steps=plan_step_count(plan),
        step_number=step_number,
    )


def _after_call_committed(*, cursor: object, plan: object, total_steps: int) -> None:
    if total_steps < 1:
        task = make_scrivener_call_completed(cursor=cursor, completed_after_step=0)
        task.save()
        scrivener_inbox.post(str(task.key))
        return

    task = make_worker_step(
        cursor=cursor,
        plan=plan,
        step_number=1,
        input_key=str(ResultsIndex(f"results:{cursor.identity}:index").input_key_for_step(1)),
    )
    task.save()
    worker_inbox.post(str(task.key))


def _after_step_committed(
    *,
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
        task.save()
        scrivener_inbox.post(str(task.key))
        return

    task = make_worker_step(
        cursor=cursor,
        plan=plan,
        step_number=next_step,
        input_key=str(ResultsIndex(f"results:{cursor.identity}:index").input_key_for_step(next_step)),
    )
    task.save()
    worker_inbox.post(str(task.key))


__all__ = ["handle"]
