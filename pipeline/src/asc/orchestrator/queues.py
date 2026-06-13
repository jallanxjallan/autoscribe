from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from asc.state import orchestrator_index, orchestrator_queue, worker_outcome_queue, worker_queue


@dataclass(frozen=True, slots=True)
class ClaimedSignal:
    cursor_key: str
    score: float | None = None

    @property
    def identity(self) -> str:
        return self.cursor_key


# Orchestrator pending queue: enqueue/retry -> orchestrator ------------------


def enqueue_orchestrator(cursor_key: str, *, score: float | None = None) -> int:
    return orchestrator_queue.enqueue(cursor_key, score=score)


def schedule_orchestrator(cursor_key: str, *, score: float | None = None) -> int:
    return enqueue_orchestrator(cursor_key, score=score)


def schedule_orchestrator_after(cursor_key: str, *, delay_seconds: float) -> int:
    return orchestrator_queue.schedule_after(cursor_key, delay_seconds=delay_seconds)


def claim_orchestrator_pending(*, limit: int = 100) -> list[ClaimedSignal]:
    return [
        ClaimedSignal(cursor_key=_claimed_key(item), score=getattr(item, "score", None))
        for item in orchestrator_queue.claim_due(limit=limit)
    ]


# Passive active cursor index ------------------------------------------------


def touch_active(cursor_key: str, *, score: float | None = None) -> int:
    return orchestrator_index.touch(cursor_key, score=score)


def remove_active(cursor_key: str) -> int:
    return orchestrator_index.remove(cursor_key)


def claim_active_stale(
    *,
    limit: int = 100,
    stale_after_seconds: float = 30.0,
    lease_seconds: float = 30.0,
) -> list[ClaimedSignal]:
    return [
        ClaimedSignal(cursor_key=_claimed_key(item), score=getattr(item, "score", None))
        for item in orchestrator_index.claim_stale(
            limit=limit,
            stale_after_seconds=stale_after_seconds,
            lease_seconds=lease_seconds,
        )
    ]


def mark_complete(cursor_key: str, *, ttl_seconds: float | None = None) -> int:
    return remove_active(cursor_key)


# Worker dispatch queue: orchestrator -> workers ----------------------------


def enqueue_worker(cursor_key: str, *, score: float | None = None) -> int:
    return worker_queue.enqueue(cursor_key, score=score)


# Worker outcome queue: workers -> orchestrator -----------------------------


def enqueue_outcome(cursor_key: str, *, score: float | None = None) -> int:
    return worker_outcome_queue.enqueue(cursor_key, score=score)


def claim_outcome() -> ClaimedSignal | None:
    claimed = worker_outcome_queue.claim_next()
    if claimed is None:
        return None
    return ClaimedSignal(cursor_key=_claimed_key(claimed), score=getattr(claimed, "score", None))


# Compatibility names --------------------------------------------------------


def index_cursor(cursor_key: str, *, score: float | None = None) -> int:
    """Compatibility alias for the passive active cursor index."""
    return touch_active(cursor_key, score=score)


def claim_index_due(*, limit: int = 100, lease_seconds: float = 30.0) -> list[ClaimedSignal]:
    """Compatibility alias for stale active-cursor supervision.

    Normal work must use claim_orchestrator_pending() or claim_outcome().
    """
    return claim_active_stale(
        limit=limit,
        stale_after_seconds=lease_seconds,
        lease_seconds=lease_seconds,
    )


def requeue(cursor_key: str, *, score: float | None = None, delay_seconds: float = 0.0) -> int:
    if score is not None:
        return enqueue_orchestrator(cursor_key, score=score)
    return enqueue_orchestrator(cursor_key, score=time.time() + max(0.0, float(delay_seconds)))


def claim() -> ClaimedSignal | None:
    """Compatibility alias: claim one worker outcome."""
    return claim_outcome()


def _claimed_key(claimed: Any) -> str:
    value = getattr(claimed, "cursor_key", None)
    if value is None:
        value = getattr(claimed, "identity", None)
    if value is None:
        value = getattr(claimed, "call_state_key", None)
    if value is None:
        value = getattr(claimed, "key", None)
    if value is None:
        value = claimed
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    if not isinstance(value, str) or not value.strip():
        raise TypeError("queue/index claim must provide a full RuntimeCursor key")
    return value.strip()


__all__ = [
    "ClaimedSignal",
    "claim",
    "claim_active_stale",
    "claim_index_due",
    "claim_orchestrator_pending",
    "claim_outcome",
    "enqueue_orchestrator",
    "enqueue_outcome",
    "enqueue_worker",
    "index_cursor",
    "mark_complete",
    "requeue",
    "remove_active",
    "schedule_orchestrator",
    "schedule_orchestrator_after",
    "touch_active",
]
