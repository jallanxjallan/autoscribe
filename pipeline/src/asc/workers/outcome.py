from __future__ import annotations

from asc.state import orchestrator_queue


def submit_outcome(job_key: str) -> int:
    """Return a completed worker job to orchestrator custody."""

    return orchestrator_queue.insert(job_key)


__all__ = ["submit_outcome"]
