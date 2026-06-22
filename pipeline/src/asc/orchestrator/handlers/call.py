"""Handle a newly posted call notice.

The enqueuer creates the Call and posts ``call:<identity>``. The orchestrator
owns runtime state, so this handler opens the Call, opens its Plan, creates the
cursor and results index, and schedules the initial scrivener write_call task.
"""

from asc.models.control.plan import Plan
from asc.models.process.call import Call
from asc.models.process.cursor import Cursor
from asc.scrivener import inbox as scrivener_inbox
from asc.state.cursor import active_cursor_index, set_cursor_key
from asc.state.results import ResultsIndex

from ..tasks import make_scrivener_write_call, plan_step_count


def handle(identity: str) -> None:
    call = Call.load(f"call:{identity}")
    plan_key = str(call.plan_key)
    plan = Plan.load(plan_key)
    total_steps = plan_step_count(plan)

    cursor = Cursor(
        identity=call.redis_key.identity,
        call_key=str(call.redis_key),
        plan_key=plan_key,
    )
    cursor.save()

    cursor_key = str(cursor.redis_key)
    set_cursor_key(identity=cursor.identity, cursor_key=cursor_key)
    active_cursor_index.schedule(cursor_key)

    ResultsIndex.create(
        call_key=call.redis_key,
        total_steps=total_steps,
    )

    task = make_scrivener_write_call(cursor)
    task.save()
    scrivener_inbox.post(str(task.redis_key))


__all__ = ["handle"]
