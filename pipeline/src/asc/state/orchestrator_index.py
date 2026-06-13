# asc/state/orchestrator_index.py
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Iterable

from asc.redis.key import RedisKey


RUNTIME_ACTIVE_INDEX_KEY = "state:runtime:active"
# Backward-compatible name for older imports.
ORCHESTRATOR_DUE_INDEX_KEY = RUNTIME_ACTIVE_INDEX_KEY
DEFAULT_STALE_AFTER_SECONDS = 30.0


@dataclass(frozen=True, slots=True)
class ActiveCursor:
    cursor_key: str
    score: float

    @property
    def identity(self) -> str:
        return self.cursor_key

    @property
    def due_at(self) -> float:
        return self.score


# Backward-compatible type alias.
DueCursor = ActiveCursor


def _index() -> RedisKey:
    return RedisKey(RUNTIME_ACTIVE_INDEX_KEY)


def _clean_key(cursor_key: str) -> str:
    if not isinstance(cursor_key, str) or not cursor_key.strip():
        raise TypeError("cursor_key must be a non-empty RuntimeCursor key")
    if ":" not in cursor_key:
        raise ValueError("cursor_key must be a full Redis key, not a bare identity")
    return cursor_key.strip()


def _score(score: float | None = None) -> float:
    return float(time.time() if score is None else score)


def active_index_key() -> str:
    return RUNTIME_ACTIVE_INDEX_KEY


def due_index_key() -> str:
    return RUNTIME_ACTIVE_INDEX_KEY


def touch(cursor_key: str, *, score: float | None = None) -> int:
    """Record that a cursor is live.

    The score is last-seen/check-at metadata for supervision only. This index is
    never a normal work queue.
    """
    return _index().zadd({_clean_key(cursor_key): _score(score)})


def schedule(cursor_key: str, *, score: float | None = None) -> int:
    return touch(cursor_key, score=score)


def enqueue(cursor_key: str, *, score: float | None = None) -> int:
    return touch(cursor_key, score=score)


def reschedule(cursor_key: str, *, delay_seconds: float = 0.0) -> int:
    return touch(cursor_key, score=time.time() + max(0.0, float(delay_seconds)))


def claim_stale(
    *,
    now: float | None = None,
    stale_after_seconds: float = DEFAULT_STALE_AFTER_SECONDS,
    lease_seconds: float = DEFAULT_STALE_AFTER_SECONDS,
    limit: int = 100,
) -> list[ActiveCursor]:
    """Return stale active cursors and advance their score to avoid spin."""
    if limit <= 0:
        return []

    cutoff = _score(now) - max(0.0, float(stale_after_seconds))
    rows = _index().zrangebyscore(
        "-inf",
        cutoff,
        start=0,
        num=int(limit),
        withscores=True,
    )
    if not rows:
        return []

    lease_until = _score(now) + max(0.0, float(lease_seconds))
    claimed: list[ActiveCursor] = []
    for raw_key, raw_score in rows:
        cursor_key = _clean_key(str(raw_key))
        _index().zadd({cursor_key: lease_until})
        claimed.append(ActiveCursor(cursor_key=cursor_key, score=float(raw_score)))
    return claimed


def claim_due(*, now: float | None = None, limit: int = 100) -> list[ActiveCursor]:
    return claim_stale(now=now, stale_after_seconds=0.0, limit=limit)


def claim_next() -> ActiveCursor | None:
    rows = claim_stale(limit=1)
    return rows[0] if rows else None


def peek_stale(
    *,
    now: float | None = None,
    stale_after_seconds: float = DEFAULT_STALE_AFTER_SECONDS,
    limit: int = 100,
) -> list[ActiveCursor]:
    if limit <= 0:
        return []
    cutoff = _score(now) - max(0.0, float(stale_after_seconds))
    rows = _index().zrangebyscore(
        "-inf",
        cutoff,
        start=0,
        num=int(limit),
        withscores=True,
    )
    return [ActiveCursor(cursor_key=_clean_key(str(k)), score=float(s)) for k, s in rows]


def peek_due(*, now: float | None = None, limit: int = 100) -> list[ActiveCursor]:
    return peek_stale(now=now, stale_after_seconds=0.0, limit=limit)


def peek_next() -> ActiveCursor | None:
    rows = peek_stale(limit=1)
    return rows[0] if rows else None


def remove(cursor_key: str) -> int:
    return _index().zrem(_clean_key(cursor_key))


def count() -> int:
    return _index().zcard()


def clear() -> int:
    return _index().delete()


def scheduled(items: Iterable[str]) -> int:
    now = time.time()
    mapping = {_clean_key(item): now for item in items}
    if not mapping:
        return 0
    return _index().zadd(mapping)


__all__ = [
    "ActiveCursor",
    "DEFAULT_STALE_AFTER_SECONDS",
    "DueCursor",
    "ORCHESTRATOR_DUE_INDEX_KEY",
    "RUNTIME_ACTIVE_INDEX_KEY",
    "active_index_key",
    "claim_due",
    "claim_next",
    "claim_stale",
    "clear",
    "count",
    "due_index_key",
    "enqueue",
    "peek_due",
    "peek_next",
    "peek_stale",
    "remove",
    "reschedule",
    "schedule",
    "scheduled",
    "touch",
]
