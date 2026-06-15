# asc/state/orchestrator_queue.py
from __future__ import annotations

from collections.abc import Sequence

from asc.state.queue import QueuedKey, RedisQueue


ORCHESTRATOR_QUEUE_KEY = "state:orchestrator:queue"


class OrchestratorQueue(RedisQueue):
    KEY = ORCHESTRATOR_QUEUE_KEY


_QUEUE = OrchestratorQueue()


def orchestrator_queue_key() -> str:
    return ORCHESTRATOR_QUEUE_KEY


def insert(cursor_key: str) -> int:
    return _QUEUE.insert(cursor_key)


def insert_many(cursor_keys: Sequence[str]) -> int:
    return _QUEUE.insert_many(cursor_keys)


def claim() -> QueuedKey | None:
    return _QUEUE.claim()


def block_claim(*, timeout: int = 0) -> QueuedKey | None:
    return _QUEUE.block_claim(timeout=timeout)


def peek() -> QueuedKey | None:
    return _QUEUE.peek()


def remove(cursor_key: str) -> int:
    return _QUEUE.remove(cursor_key)


def count() -> int:
    return _QUEUE.count()


def clear() -> int:
    return _QUEUE.clear()


__all__ = [
    "ORCHESTRATOR_QUEUE_KEY",
    "OrchestratorQueue",
    "QueuedKey",
    "block_claim",
    "claim",
    "clear",
    "count",
    "insert",
    "insert_many",
    "orchestrator_queue_key",
    "peek",
    "remove",
]
