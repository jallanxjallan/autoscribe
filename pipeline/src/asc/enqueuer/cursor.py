from __future__ import annotations

from asc.models.process.cursor import Cursor
from asc.orchestrator.inbox import post
from asc.state.cursor_index import (
    active_cursor_index,
    set_cursor_key,
)


def create_runtime_cursor(*, identity: str, call_key: str, plan_key: str) -> Cursor:
    if not isinstance(identity, str) or not identity.strip():
        raise ValueError("identity must be non-empty")
    if not isinstance(call_key, str) or not call_key.strip():
        raise ValueError("call_key must be non-empty")
    if not isinstance(plan_key, str) or not plan_key.strip():
        raise ValueError("plan_key must be non-empty")

    cursor = Cursor(
        identity=identity.strip(),
        call_key=call_key.strip(),
        plan_key=plan_key.strip(),
    )
    cursor.save()
    return cursor


def insert_runtime_cursor(
    *,
    identity: str,
    call_key: str,
    plan_key: str,
) -> str:
    """Create a runtime Cursor and submit it to the orchestrator inbox.

    This is the enqueuer boundary.

    The enqueuer owns initial runtime state creation. It creates the cursor,
    registers identity -> cursor_key, marks the cursor active for supervision,
    and posts the cursor key to the orchestrator inbox.

    It does not call the legacy orchestrator queue directly.
    """

    cursor = create_runtime_cursor(
        identity=identity,
        call_key=call_key,
        plan_key=plan_key,
    )

    cursor_key = str(cursor.redis_key)

    set_cursor_key(identity=cursor.identity, cursor_key=cursor_key)
    active_cursor_index.schedule(cursor_key)
    post(cursor_key)

    return cursor_key


def insert_runtime_cursor_in_orchestrator_inbox(cursor_key: str) -> int:
    """Post an existing runtime Cursor key to the orchestrator inbox.

    Prefer insert_runtime_cursor() when the enqueuer is creating a new cursor.
    This helper is only for cases where the cursor already exists.
    """

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