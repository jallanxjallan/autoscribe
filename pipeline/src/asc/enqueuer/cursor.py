from asc.models.process.cursor import Cursor
from asc.orchestrator.inbox import post
from asc.redis.key import RedisKey
from asc.state.cursor import (
    active_cursor_index,
    set_cursor_key,
)


def create_runtime_cursor(*, call_key: RedisKey, plan_key: str) -> Cursor:
    """Create and persist a runtime Cursor for the Call key identity."""

    if not call_key.identity:
        raise ValueError("call_key.identity must be non-empty")
    if not isinstance(plan_key, str) or not plan_key.strip():
        raise ValueError("plan_key must be non-empty")

    cursor = Cursor(
        identity=call_key.identity,
        call_key=str(call_key),
        plan_key=plan_key.strip(),
    )
    cursor.save()
    return cursor


def insert_runtime_cursor(
    *,
    call_key: RedisKey,
    plan_key: str,
) -> str:
    """Create a runtime Cursor and submit it to the orchestrator inbox."""

    cursor = create_runtime_cursor(
        call_key=call_key,
        plan_key=plan_key,
    )

    set_cursor_key(identity=cursor.identity, cursor_key=str(cursor.redis_key))
    active_cursor_index.schedule(str(cursor.redis_key))
    post(str(cursor.redis_key))

    return str(cursor.redis_key)


def insert_runtime_cursor_in_orchestrator_inbox(cursor_key: str) -> int:
    """Post an existing runtime Cursor key to the orchestrator inbox."""

    if not isinstance(cursor_key, str) or not cursor_key.strip():
        raise ValueError("cursor_key must be a non-empty full Redis key")
    if ":" not in cursor_key:
        raise ValueError(f"cursor_key must be a full Redis key: {cursor_key!r}")

    return post(cursor_key)


__all__ = [
    "create_runtime_cursor",
    "insert_runtime_cursor",
    "insert_runtime_cursor_in_orchestrator_inbox",
]
