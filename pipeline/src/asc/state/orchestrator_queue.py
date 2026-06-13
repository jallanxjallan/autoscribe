# asc/state/orchestrator_queue.py
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Iterable

import redis


ORCHESTRATOR_PENDING_QUEUE_KEY = "state:orchestrator:pending"
# Backward-compatible constant name for callers that display/count this module.
ORCHESTRATOR_QUEUE_KEY = ORCHESTRATOR_PENDING_QUEUE_KEY


@dataclass(frozen=True, slots=True)
class PendingCursor:
    cursor_key: str
    score: float

    @property
    def key(self) -> str:
        return self.cursor_key

    @property
    def identity(self) -> str:
        return self.cursor_key


def _redis() -> redis.Redis:
    return redis.Redis(decode_responses=True)


def _clean_key(cursor_key: str) -> str:
    if not isinstance(cursor_key, str) or not cursor_key.strip():
        raise TypeError("cursor_key must be a non-empty RuntimeCursor key")
    if ":" not in cursor_key:
        raise ValueError("cursor_key must be a full Redis key, not a bare identity")
    return cursor_key.strip()


def _score(score: float | None = None) -> float:
    return float(time.time() if score is None else score)


def orchestrator_queue_key() -> str:
    return ORCHESTRATOR_PENDING_QUEUE_KEY


def pending_queue_key() -> str:
    return ORCHESTRATOR_PENDING_QUEUE_KEY


def insert(key: str, *, score: float | None = None) -> int:
    """Put a cursor under orchestrator custody.

    This is a real work queue, not the active cursor index. Members are removed
    when claimed. Use asc.state.orchestrator_index for passive monitoring.
    """
    return int(_redis().zadd(ORCHESTRATOR_PENDING_QUEUE_KEY, {_clean_key(key): _score(score)}))


def enqueue(key: str, *, score: float | None = None) -> int:
    return insert(key, score=score)


def schedule(key: str, *, score: float | None = None) -> int:
    return insert(key, score=score)


def schedule_after(key: str, *, delay_seconds: float) -> int:
    return insert(key, score=time.time() + max(0.0, float(delay_seconds)))


def claim_due(*, now: float | None = None, limit: int = 100) -> list[PendingCursor]:
    """Claim due cursors by removing them from the pending queue."""
    if limit <= 0:
        return []

    r = _redis()
    rows = r.zrangebyscore(
        ORCHESTRATOR_PENDING_QUEUE_KEY,
        "-inf",
        _score(now),
        start=0,
        num=int(limit),
        withscores=True,
    )
    claimed: list[PendingCursor] = []
    for raw_key, raw_score in rows:
        cursor_key = _clean_key(str(raw_key))
        if r.zrem(ORCHESTRATOR_PENDING_QUEUE_KEY, cursor_key) == 1:
            claimed.append(PendingCursor(cursor_key=cursor_key, score=float(raw_score)))
    return claimed


def claim() -> PendingCursor | None:
    rows = claim_due(limit=1)
    return rows[0] if rows else None


def claim_next() -> PendingCursor | None:
    return claim()


def due(*, now: float | None = None, limit: int = 100) -> list[PendingCursor]:
    if limit <= 0:
        return []
    rows = _redis().zrangebyscore(
        ORCHESTRATOR_PENDING_QUEUE_KEY,
        "-inf",
        _score(now),
        start=0,
        num=int(limit),
        withscores=True,
    )
    return [PendingCursor(cursor_key=_clean_key(str(k)), score=float(s)) for k, s in rows]


def peek() -> PendingCursor | None:
    rows = due(limit=1)
    return rows[0] if rows else None


def peek_next() -> PendingCursor | None:
    return peek()


def remove(key: str) -> int:
    return int(_redis().zrem(ORCHESTRATOR_PENDING_QUEUE_KEY, _clean_key(key)))


def count() -> int:
    return int(_redis().zcard(ORCHESTRATOR_PENDING_QUEUE_KEY))


def clear() -> int:
    return int(_redis().delete(ORCHESTRATOR_PENDING_QUEUE_KEY))


def enqueue_batch(keys: Iterable[str], *, score: float | None = None) -> int:
    mapping = {_clean_key(key): _score(score) for key in keys}
    if not mapping:
        return 0
    return int(_redis().zadd(ORCHESTRATOR_PENDING_QUEUE_KEY, mapping))


# Compatibility names from the old index-shaped module.
index_key = pending_queue_key
index_many = enqueue_batch
mark_complete = remove


__all__ = [
    "ORCHESTRATOR_PENDING_QUEUE_KEY",
    "ORCHESTRATOR_QUEUE_KEY",
    "PendingCursor",
    "claim",
    "claim_due",
    "claim_next",
    "clear",
    "count",
    "due",
    "enqueue",
    "enqueue_batch",
    "index_key",
    "index_many",
    "insert",
    "mark_complete",
    "orchestrator_queue_key",
    "pending_queue_key",
    "peek",
    "peek_next",
    "remove",
    "schedule",
    "schedule_after",
]
