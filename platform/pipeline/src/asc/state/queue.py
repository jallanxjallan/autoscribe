"""Generic Redis LIST plumbing for package-owned queues and inboxes.

This module deliberately does not define named AutoScribe queues. Owning
packages declare their own fixed Redis keys, for example::

    class Inbox(RedisQueue):
        KEY = "control:orchestrator:inbox"

    class Queue(RedisQueue):
        KEY = "control:worker:queue"

``asc.state`` provides only the reusable LIST mechanics: validation, insert,
claim, blocking claim, peek, remove, count, and clear.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from asc.core.timestamp import timestamp
from asc.redis.index_base import FixedRedisIndex
from asc.redis.primitives import lists


@dataclass(frozen=True, slots=True)
class QueuedKey:
    """One claimed daemon queue item.

    Queue entries are full Redis keys. The owning package decides whether those
    keys are cursors, tasks, markers, or another model kind. The score is a local
    timestamp for diagnostics; LIST queues do not persist per-item scores.
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


def daemon_timeout_seconds(default: int = 5) -> int:
    return max(1, int(default))


def daemon_idle_seconds(default: int = 3600) -> int:
    """Seconds a daemon may sit idle before returning None."""

    return max(1, int(default))


def daemon_empty_limit(*, timeout: int | None = None, default: int | None = None) -> int:
    """Return empty BLPOP cycles before a daemon may exit."""

    cycle_timeout = daemon_timeout_seconds() if timeout is None else max(1, int(timeout))
    if default is not None:
        return max(1, int(default))
    return max(1, daemon_idle_seconds() // cycle_timeout)


class RedisQueue(FixedRedisIndex):
    """Small Redis LIST FIFO queue for daemon handoff.

    RedisKey remains the key value object and central client access point.
    LIST primitives live here because queues are the modules that use them.
    """

    KEY: str

    def rpush(self, *values: str) -> int:
        if not values:
            raise ValueError("rpush() requires at least one value")
        members = tuple(
            require_queue_key(value, field_name=f"values[{index}]")
            for index, value in enumerate(values)
        )
        return lists.rpush(self.key, *members)

    def lpop(self) -> str | None:
        return lists.lpop(self.key)

    def blpop(self, *, timeout: int = 0) -> tuple[str, str] | None:
        if not isinstance(timeout, int) or timeout < 0:
            raise ValueError("blpop() timeout must be a non-negative int")

        item = lists.blpop(self.key, timeout=timeout)
        if item is None:
            return None

        key, value = item
        return str(key), str(value)

    def lindex(self, index: int) -> str | None:
        return lists.lindex(self.key, int(index))

    def lrem(self, value: str, *, count: int = 0) -> int:
        return lists.lrem(self.key, require_queue_key(value), count=int(count))

    def llen(self) -> int:
        return lists.llen(self.key)

    def insert(self, key: str) -> int:
        return self.rpush(key)

    def insert_many(self, keys: Sequence[str]) -> int:
        members = [
            require_queue_key(key, field_name=f"keys[{index}]")
            for index, key in enumerate(keys)
        ]
        if not members:
            return 0
        return self.rpush(*members)

    def claim(self) -> QueuedKey | None:
        key = self.lpop()
        if key is None:
            return None
        return QueuedKey(key=key, score=float(timestamp()))

    def block_claim(self, *, timeout: int = 0) -> QueuedKey | None:
        item = self.blpop(timeout=timeout)
        if item is None:
            return None
        _queue_key, value = item
        return QueuedKey(key=value, score=float(timestamp()))

    def daemon_claim(
        self,
        *,
        timeout: int | None = None,
        empty_limit: int | None = None,
    ) -> QueuedKey | None:
        """Wait for the first daemon handoff item across bounded empty cycles."""

        cycle_timeout = daemon_timeout_seconds() if timeout is None else max(1, int(timeout))
        max_empty = daemon_empty_limit(timeout=cycle_timeout)
        if empty_limit is not None:
            max_empty = int(empty_limit)
        if max_empty <= 0:
            return None

        for _ in range(max_empty):
            claimed = self.block_claim(timeout=cycle_timeout)
            if claimed is not None:
                return claimed
        return None

    def daemon_drain_claim(self) -> QueuedKey | None:
        """Claim immediately while draining pending daemon work."""

        return self.claim()

    def peek(self) -> QueuedKey | None:
        key = self.lindex(0)
        if key is None:
            return None
        return QueuedKey(key=key, score=float(timestamp()))

    def remove(self, key: str) -> int:
        return self.lrem(key)

    def count(self) -> int:
        return self.llen()

    def clear(self) -> int:
        return int(self.delete())


__all__ = [
    "QueuedKey",
    "RedisQueue",
    "daemon_empty_limit",
    "daemon_idle_seconds",
    "daemon_timeout_seconds",
    "require_queue_key",
]
