# asc/state/queue.py
"""Redis-backed process custody state.

Invariant:
    one daemon, one inbound queue

Queues:
    state:orchestrator:queue  -> cursor keys for orchestrator
    state:worker:queue        -> cursor keys for workers
    state:scrivener:queue     -> cursor keys for scrivener

Non-queue state:
    state:cursor:active      -> active cursor watchdog zset
    state:slugmap            -> slug -> Redis key resolver

All daemon queues contain cursor keys only. Job/instruction records, when
needed, live outside the queues and are derived from the cursor identity.
"""


from collections.abc import Sequence
from dataclasses import dataclass
import os

from asc.core.timestamp import timestamp
from asc.redis.index_base import FixedRedisIndex


@dataclass(frozen=True, slots=True)
class QueuedKey:
    """One claimed daemon queue item.

    Daemon queues contain full Redis keys. Only orchestrator ingress from enqueue
    may be a cursor key; after activation, all daemon handoff items are job keys.
    The score is a local claim timestamp for diagnostics; LIST queues do not
    persist per-item scores.
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
    value = os.environ.get("AUTOSCRIBE_DAEMON_CLAIM_TIMEOUT")
    if value is None:
        return default
    return max(1, int(value))


def daemon_idle_seconds(default: int = 3600) -> int:
    """Seconds a daemon may sit idle before returning None.

    Development default is deliberately long: daemons should stay alive while
    you inspect Redis, ledger rows, and logs. Stop commands should be the normal
    way to end them.
    """

    value = os.environ.get("AUTOSCRIBE_DAEMON_IDLE_SECONDS")
    if value is None:
        return default
    return max(1, int(value))


def daemon_empty_limit(*, timeout: int | None = None, default: int | None = None) -> int:
    """Return empty BLPOP cycles before a daemon may exit.

    ``AUTOSCRIBE_DAEMON_EMPTY_LIMIT`` is still honored for compatibility, but
    the default is now derived from ``AUTOSCRIBE_DAEMON_IDLE_SECONDS``.
    """

    value = os.environ.get("AUTOSCRIBE_DAEMON_EMPTY_LIMIT")
    if value is not None:
        return max(1, int(value))

    cycle_timeout = daemon_timeout_seconds() if timeout is None else max(1, int(timeout))
    if default is not None:
        return max(1, int(default))
    return max(1, daemon_idle_seconds() // cycle_timeout)


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

    def daemon_claim(
        self,
        *,
        timeout: int | None = None,
        empty_limit: int | None = None,
    ) -> QueuedKey | None:
        """Wait for the first daemon handoff item across bounded empty cycles.

        Use this only when a command first starts and there may be no queue yet.
        Once a daemon has claimed work, switch back to ``claim()`` so the command
        drains already-pending items and returns to the shell on the first empty
        queue instead of sitting through another idle window.
        """

        cycle_timeout = daemon_timeout_seconds() if timeout is None else max(1, int(timeout))
        idle_limit = daemon_empty_limit(timeout=cycle_timeout)
        requested_limit = idle_limit if empty_limit is None else max(1, int(empty_limit))
        max_empty = max(idle_limit, requested_limit)

        for _ in range(max_empty):
            claimed = self.block_claim(timeout=cycle_timeout)
            if claimed is not None:
                return claimed
        return None

    def daemon_drain_claim(self) -> QueuedKey | None:
        """Claim immediately while draining pending daemon work.

        This is deliberately non-blocking. It preserves CLI behavior: process all
        pending queue entries, then print the empty message and return control to
        the shell.
        """

        return self.claim()

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


def daemon_claim(
    queue: RedisQueue,
    *,
    timeout: int | None = None,
    empty_limit: int | None = None,
) -> QueuedKey | None:
    return queue.daemon_claim(timeout=timeout, empty_limit=empty_limit)


def daemon_drain_claim(queue: RedisQueue) -> QueuedKey | None:
    return queue.daemon_drain_claim()


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
    "daemon_claim",
    "daemon_drain_claim",
    "daemon_empty_limit",
    "daemon_idle_seconds",
    "daemon_timeout_seconds",
    "claim",
    "clear",
    "count",
    "insert",
    "insert_many",
    "peek",
    "remove",
    "require_queue_key",
]
