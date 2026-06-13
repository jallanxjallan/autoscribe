from __future__ import annotations

from asc.state import worker_outcome_queue


def submit_outcome(cursor_key: str) -> int:
    return worker_outcome_queue.enqueue(cursor_key)


__all__ = ["submit_outcome"]
