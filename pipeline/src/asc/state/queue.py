# asc/state/queue.py
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from asc.core.timestamp import timestamp
from asc.redis.index_base import FixedRedisIndex


@dataclass(frozen=True, slots=True)
class QueuedKey:
    """One claimed daemon queue item.

    Daemon queues contain full Redis cursor keys only. The score is a local
    claim timestamp for diagnostics; LIST queues do not persist per-item scores.
    """

    key: str
    score: float

    @property
    def cursor_key(self) -> str:
        return self.key

    @property
    def identity(self) -> str:
        return self.key


def require_queue_key(value: object, *, field_name: str = "key") -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")

    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} must be non-empty")
    if ":" not in text:
        raise ValueError(f"{field_name} must be a full Redis key, not a bare identity")

    return text


class RedisQueue(FixedRedisIndex):
    """Small Redis LIST FIFO queue for daemon handoff.

    This class is intentionally narrow. Scheduling, retries, and watchdog state
    do not belong in live handoff queues.
    """

    KEY: str

    def insert(self, key: str) -> int:
        return int(self.key.rpush(require_queue_key(key)))

    def insert_many(self, keys: Sequence[str]) -> int:
        members = [
            require_queue_key(key, field_name=f"keys[{index}]")
            for index, key in enumerate(keys)
        ]
        if not members:
            return 0
        return int(self.key.rpush(*members))

    def claim(self) -> QueuedKey | None:
        key = self.key.lpop()
        if key is None:
            return None
        return QueuedKey(key=str(key), score=float(timestamp()))

    def block_claim(self, *, timeout: int = 0) -> QueuedKey | None:
        item = self.key.blpop(timeout=timeout)
        if item is None:
            return None
        _queue_key, value = item
        return QueuedKey(key=str(value), score=float(timestamp()))

    def peek(self) -> QueuedKey | None:
        key = self.key.lindex(0)
        if key is None:
            return None
        return QueuedKey(key=str(key), score=float(timestamp()))

    def remove(self, key: str) -> int:
        return int(self.key._r().lrem(self.KEY, 0, require_queue_key(key)))

    def count(self) -> int:
        return int(self.key.llen())

    def clear(self) -> int:
        return int(self.delete())


def insert(queue: RedisQueue, key: str) -> int:
    return queue.insert(key)


def insert_many(queue: RedisQueue, keys: Sequence[str]) -> int:
    return queue.insert_many(keys)


def claim(queue: RedisQueue) -> QueuedKey | None:
    return queue.claim()


def block_claim(queue: RedisQueue, *, timeout: int = 0) -> QueuedKey | None:
    return queue.block_claim(timeout=timeout)


def peek(queue: RedisQueue) -> QueuedKey | None:
    return queue.peek()


def remove(queue: RedisQueue, key: str) -> int:
    return queue.remove(key)


def count(queue: RedisQueue) -> int:
    return queue.count()


def clear(queue: RedisQueue) -> int:
    return queue.clear()


__all__ = [
    "QueuedKey",
    "RedisQueue",
    "block_claim",
    "claim",
    "clear",
    "count",
    "insert",
    "insert_many",
    "peek",
    "remove",
    "require_queue_key",
]
