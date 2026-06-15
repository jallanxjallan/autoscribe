from __future__ import annotations

from asc.state import orchestrator_queue


def submit_outcome(cursor_key: str) -> int:
    """Return a completed worker cursor to orchestrator custody."""

    return orchestrator_queue.insert(cursor_key)


__all__ = ["submit_outcome"]
