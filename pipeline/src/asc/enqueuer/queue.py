from __future__ import annotations

from asc.state.orchestrator_queue import insert as enqueue_orchestrator


def enqueue_cursor(cursor_key: str) -> None:
    if not isinstance(cursor_key, str) or not cursor_key.strip():
        raise ValueError("cursor_key must be a non-empty full Redis key")
    if ":" not in cursor_key:
        raise ValueError(f"cursor_key must be a full Redis key: {cursor_key!r}")

    enqueue_orchestrator(cursor_key.strip())


__all__ = ["enqueue_cursor"]
