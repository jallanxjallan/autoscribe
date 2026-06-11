# asc/state/orchestrator_queue.py
from __future__ import annotations

from asc.state.queue import QueuedKey, RedisQueue


ORCHESTRATOR_QUEUE_KEY = "queue:orchestrator:pending"


class QueuedCallState(QueuedKey):
    @property
    def call_state_key(self) -> str:
        return self.key


class OrchestratorQueue(RedisQueue):
    KEY = ORCHESTRATOR_QUEUE_KEY

    def claim_next(self) -> QueuedCallState | None:
        claimed = super().claim_next()
        if claimed is None:
            return None
        return QueuedCallState(key=claimed.key, score=claimed.score)

    def peek_next(self) -> QueuedCallState | None:
        peeked = super().peek_next()
        if peeked is None:
            return None
        return QueuedCallState(key=peeked.key, score=peeked.score)


_QUEUE = OrchestratorQueue()


def orchestrator_queue_key() -> str:
    return ORCHESTRATOR_QUEUE_KEY


def enqueue(key: str, *, score: float | None = None) -> int:
    return _QUEUE.enqueue(key, score=score)


def enqueue_batch(*args, **kwargs) -> int:
    return _QUEUE.enqueue_batch(*args, **kwargs)


def claim_next() -> QueuedCallState | None:
    return _QUEUE.claim_next()


def peek_next() -> QueuedCallState | None:
    return _QUEUE.peek_next()


def count() -> int:
    return _QUEUE.count()


def clear() -> int:
    return _QUEUE.clear()


__all__ = [
    "ORCHESTRATOR_QUEUE_KEY",
    "OrchestratorQueue",
    "QueuedCallState",
    "claim_next",
    "clear",
    "count",
    "enqueue",
    "enqueue_batch",
    "orchestrator_queue_key",
    "peek_next",
]