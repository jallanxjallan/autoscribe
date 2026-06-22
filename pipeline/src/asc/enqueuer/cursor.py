from asc.models.control.plan import Plan
from asc.models.process.call import Call
from asc.models.process.cursor import Cursor
from asc.orchestrator.inbox import post
from asc.state.cursor import (
    active_cursor_index,
    set_cursor_key,
)


def create_runtime_cursor(*, call: Call, plan: Plan) -> Cursor:
    """Create and persist a runtime Cursor for the Call/Plan pair.

    Call and Plan stay as model instances until the Cursor record needs to store
    their raw Redis keys as fields.
    """

    call_key = call.redis_key
    plan_key = plan.redis_key

    if not call_key.identity:
        raise ValueError("call.redis_key.identity must be non-empty")
    if not plan_key.identity:
        raise ValueError("plan.redis_key.identity must be non-empty")

    cursor = Cursor(
        identity=call_key.identity,
        call_key=str(call_key),
        plan_key=str(plan_key),
    )
    cursor.save()
    return cursor


def insert_runtime_cursor(
    *,
    call: Call,
    plan: Plan,
) -> Cursor:
    """Create a runtime Cursor, index it, and submit it to orchestrator."""

    cursor = create_runtime_cursor(
        call=call,
        plan=plan,
    )
    cursor_key = str(cursor.redis_key)

    set_cursor_key(identity=cursor.identity, cursor_key=cursor_key)
    active_cursor_index.schedule(cursor_key)
    post(cursor_key)

    return cursor


def insert_runtime_cursor_in_orchestrator_inbox(cursor: Cursor) -> int:
    """Post an existing runtime Cursor to the orchestrator inbox."""

    return post(str(cursor.redis_key))


__all__ = [
    "create_runtime_cursor",
    "insert_runtime_cursor",
    "insert_runtime_cursor_in_orchestrator_inbox",
]
