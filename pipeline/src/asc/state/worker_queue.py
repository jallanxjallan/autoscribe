# asc/state/worker_queue.py
from __future__ import annotations

from asc.state.queue import QueuedKey, RedisQueue


WORKER_QUEUE_KEY = "queue:worker:pending"


class QueuedStep(QueuedKey):
    @property
    def step_key(self) -> str:
        return self.key

    @property
    def identity(self) -> str:
        return self.key


class WorkerQueue(RedisQueue):
    KEY = WORKER_QUEUE_KEY

    def claim_next(self) -> QueuedStep | None:
        claimed = super().claim_next()
        if claimed is None:
            return None
        return QueuedStep(key=claimed.key, score=claimed.score)

    def peek_next(self) -> QueuedStep | None:
        peeked = super().peek_next()
        if peeked is None:
            return None
        return QueuedStep(key=peeked.key, score=peeked.score)


_QUEUE = WorkerQueue()


def worker_queue_key() -> str:
    return WORKER_QUEUE_KEY


def enqueue(key: str, *, score: float | None = None) -> int:
    return _QUEUE.enqueue(key, score=score)


def enqueue_batch(*args, **kwargs) -> int:
    return _QUEUE.enqueue_batch(*args, **kwargs)


def claim_next() -> QueuedStep | None:
    return _QUEUE.claim_next()


def peek_next() -> QueuedStep | None:
    return _QUEUE.peek_next()


def count() -> int:
    return _QUEUE.count()


def clear() -> int:
    return _QUEUE.clear()


__all__ = [
    "WORKER_QUEUE_KEY",
    "QueuedStep",
    "WorkerQueue",
    "claim_next",
    "clear",
    "count",
    "enqueue",
    "enqueue_batch",
    "peek_next",
    "worker_queue_key",
]