# asc/state/scrivener_queue.py
from __future__ import annotations

from collections.abc import Sequence

from asc.state.queue import QueuedKey, RedisQueue


SCRIVENER_QUEUE_KEY = "state:scrivener:queue"


class ScrivenerQueue(RedisQueue):
    KEY = SCRIVENER_QUEUE_KEY


_QUEUE = ScrivenerQueue()


def scrivener_queue_key() -> str:
    return SCRIVENER_QUEUE_KEY


def insert(cursor_key: str) -> int:
    return _QUEUE.insert(cursor_key)


def insert_many(cursor_keys: Sequence[str]) -> int:
    return _QUEUE.insert_many(cursor_keys)


def claim() -> QueuedKey | None:
    return _QUEUE.claim()


def block_claim(*, timeout: int = 0) -> QueuedKey | None:
    return _QUEUE.block_claim(timeout=timeout)


def daemon_claim(*, timeout: int | None = None, empty_limit: int | None = None) -> QueuedKey | None:
    return _QUEUE.daemon_claim(timeout=timeout, empty_limit=empty_limit)


def daemon_drain_claim() -> QueuedKey | None:
    return _QUEUE.daemon_drain_claim()


def peek() -> QueuedKey | None:
    return _QUEUE.peek()


def remove(cursor_key: str) -> int:
    return _QUEUE.remove(cursor_key)


def count() -> int:
    return _QUEUE.count()


def clear() -> int:
    return _QUEUE.clear()


__all__ = [
    "SCRIVENER_QUEUE_KEY",
    "ScrivenerQueue",
    "QueuedKey",
    "block_claim",
    "claim",
    "daemon_claim",
    "daemon_drain_claim",
    "clear",
    "count",
    "insert",
    "insert_many",
    "peek",
    "remove",
    "scrivener_queue_key",
]
