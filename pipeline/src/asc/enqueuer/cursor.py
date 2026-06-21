from __future__ import annotations

from asc.models.process.cursor import Cursor
from asc.state.cursor_index import CursorIndex
from asc.state import orchestrator_inbox


def create_runtime_cursor(*, identity: str, call_key: str, plan_key: str) -> Cursor:
    if not identity:
        raise ValueError("identity must be non-empty")
    if not call_key:
        raise ValueError("call_key must be non-empty")
    if not plan_key:
        raise ValueError("plan_key must be non-empty")

    cursor = Cursor(
        identity=identity,
        call_key=call_key,
        plan_key=plan_key,
    )
    cursor.save()
    return cursor


def create_cursor_index(
    *,
    identity: str,
    cursor_key: str,
    ttl_seconds: int | None = None,
) -> CursorIndex:
    """Create the cursor index and record the active Cursor for this process."""

    if not identity:
        raise ValueError("identity must be non-empty")
    if not cursor_key:
        raise ValueError("cursor_key must be non-empty")

    cursor_index = CursorIndex.create(identity=identity, ttl_seconds=ttl_seconds)
    cursor_index.set_cursor(cursor_key)
    return cursor_index


def insert_runtime_cursor_in_orchestrator_inbox(cursor_key: str) -> int:
    """Submit the fresh runtime Cursor key to the orchestrator inbox.

    Enqueuer creates runtime state and then signals the orchestrator. It must not
    use the legacy orchestrator queue helper. The inbox is the explicit boundary
    for new externally submitted cursors; later worker/scrivener completions may
    still return task keys through the orchestrator's normal routing path.
    """

    if not isinstance(cursor_key, str) or not cursor_key.strip():
        raise ValueError("cursor_key must be a non-empty full Redis key")
    if ":" not in cursor_key:
        raise ValueError(f"cursor_key must be a full Redis key: {cursor_key!r}")

    return orchestrator_inbox.insert(cursor_key.strip())


__all__ = [
    "create_cursor_index",
    "create_runtime_cursor",
    "insert_runtime_cursor_in_orchestrator_inbox",
]
