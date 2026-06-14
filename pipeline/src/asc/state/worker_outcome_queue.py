# asc/state/worker_outcome_queue.py
from __future__ import annotations

from asc.state.queue import QueuedKey, RedisQueue


WORKER_OUTCOME_QUEUE_KEY = "state:worker:outcome"


class WorkerOutcomeQueue(RedisQueue):
    KEY = WORKER_OUTCOME_QUEUE_KEY


_QUEUE = WorkerOutcomeQueue()


def worker_outcome_queue_key() -> str:
    return WORKER_OUTCOME_QUEUE_KEY


def insert(key: str, *, score: float | None = None) -> int:
    return _QUEUE.insert(key, score=score)


def enqueue(key: str, *, score: float | None = None) -> int:
    return insert(key, score=score)


def claim() -> QueuedKey | None:
    return _QUEUE.claim()


def block_claim(*, timeout: int = 0) -> QueuedKey | None:
    return _QUEUE.block_claim(timeout=timeout)


def claim_next() -> QueuedKey | None:
    return claim()


def block_claim_next(*, timeout: int = 0) -> QueuedKey | None:
    return block_claim(timeout=timeout)


def peek() -> QueuedKey | None:
    return _QUEUE.peek()


def peek_next() -> QueuedKey | None:
    return peek()


def count() -> int:
    return _QUEUE.count()


def clear() -> int:
    return _QUEUE.clear()


__all__ = [
    "WORKER_OUTCOME_QUEUE_KEY",
    "QueuedKey",
    "WorkerOutcomeQueue",
    "block_claim",
    "block_claim_next",
    "claim",
    "claim_next",
    "clear",
    "count",
    "enqueue",
    "insert",
    "peek",
    "peek_next",
    "worker_outcome_queue_key",
]
