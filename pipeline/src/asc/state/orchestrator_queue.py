# asc/state/orchestrator_queue.py
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from asc.state.queue import QueuedKey, RedisQueue


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


class OrchestratorQueue(RedisQueue):
    KEY = ORCHESTRATOR_PENDING_QUEUE_KEY


_QUEUE = OrchestratorQueue()


def _as_pending(item: QueuedKey | None) -> PendingCursor | None:
    if item is None:
        return None
    return PendingCursor(cursor_key=item.key, score=item.score)


def orchestrator_queue_key() -> str:
    return ORCHESTRATOR_PENDING_QUEUE_KEY


def pending_queue_key() -> str:
    return ORCHESTRATOR_PENDING_QUEUE_KEY


def insert(key: str, *, score: float | None = None) -> int:
    """Put a cursor under orchestrator custody.

    This is a Redis LIST work queue. Members are removed when claimed.
    Use asc.state.orchestrator_index for active-cursor monitoring, stale checks,
    or delayed/scheduled cursor metadata.
    """
    return _QUEUE.insert(key, score=score)


def enqueue(key: str, *, score: float | None = None) -> int:
    return insert(key, score=score)


def schedule(key: str, *, score: float | None = None) -> int:
    # Compatibility alias. Immediate handoff only.
    return insert(key, score=score)


def schedule_after(key: str, *, delay_seconds: float) -> int:
    if float(delay_seconds) > 0:
        raise NotImplementedError(
            "orchestrator_queue is a Redis LIST and cannot delay items; "
            "store delayed/scheduled cursor metadata in orchestrator_index instead"
        )
    return insert(key)


def claim() -> PendingCursor | None:
    return _as_pending(_QUEUE.claim())


def block_claim(*, timeout: int = 0) -> PendingCursor | None:
    return _as_pending(_QUEUE.block_claim(timeout=timeout))


def claim_next() -> PendingCursor | None:
    return claim()


def block_claim_next(*, timeout: int = 0) -> PendingCursor | None:
    return block_claim(timeout=timeout)


def claim_due(*, now: float | None = None, limit: int = 100) -> list[PendingCursor]:
    """Compatibility wrapper for old zset callers.

    LIST queues are not score-filtered. This drains up to `limit` immediately
    available items without blocking.
    """
    if limit <= 0:
        return []
    claimed: list[PendingCursor] = []
    for _ in range(int(limit)):
        item = claim()
        if item is None:
            break
        claimed.append(item)
    return claimed


def due(*, now: float | None = None, limit: int = 100) -> list[PendingCursor]:
    item = peek()
    return [] if item is None else [item]


def peek() -> PendingCursor | None:
    return _as_pending(_QUEUE.peek())


def peek_next() -> PendingCursor | None:
    return peek()


def remove(key: str) -> int:
    # Redis lists do not provide a cheap queue-position delete. If a future
    # recovery path needs this, use LREM deliberately rather than hiding it.
    from asc.state.queue import require_queue_key

    return int(_QUEUE.key._r().lrem(ORCHESTRATOR_PENDING_QUEUE_KEY, 0, require_queue_key(key)))


def count() -> int:
    return _QUEUE.count()


def clear() -> int:
    return _QUEUE.clear()


def enqueue_batch(keys: Iterable[str], *, score: float | None = None) -> int:
    return _QUEUE.insert_many(list(keys), start_score=score)


# Compatibility names from the old index-shaped module.
index_key = pending_queue_key
index_many = enqueue_batch
mark_complete = remove


__all__ = [
    "ORCHESTRATOR_PENDING_QUEUE_KEY",
    "ORCHESTRATOR_QUEUE_KEY",
    "OrchestratorQueue",
    "PendingCursor",
    "block_claim",
    "block_claim_next",
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
