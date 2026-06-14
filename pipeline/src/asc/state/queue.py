# asc/state/queue.py
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from asc.core.timestamp import timestamp
from asc.redis.index_base import FixedRedisIndex


@dataclass(frozen=True, slots=True)
class QueuedKey:
    """One claimed queue item.

    Redis LIST queues do not store scores. The score field is retained as a
    compatibility/diagnostic timestamp so older callers that read `.score` do
    not break during the zset -> list migration.
    """

    key: str
    score: float

    @property
    def identity(self) -> str:
        return self.key

    @property
    def cursor_key(self) -> str:
        return self.key

    @property
    def call_state_key(self) -> str:
        return self.key

    @property
    def step_key(self) -> str:
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
    """Small Redis LIST FIFO queue.

    Live handoff queues should block when idle. That is why this class uses
    RPUSH + LPOP/BLPOP instead of zset polling. Scheduling/watchdog state belongs
    in a separate zset index, not in the handoff queue.
    """

    KEY: str

    def insert(self, key: str, *, score: float | None = None) -> int:
        # score is accepted for compatibility with the old zset interface.
        # FIFO order is Redis list order: RPUSH at tail, LPOP/BLPOP from head.
        member = require_queue_key(key)
        return int(self.key.rpush(member))

    def insert_many(
        self,
        keys: Sequence[str],
        *,
        start_score: float | None = None,
        step: float = 0.001,
    ) -> int:
        # start_score/step are compatibility-only; list order is input order.
        members = [require_queue_key(key, field_name=f"keys[{index}]") for index, key in enumerate(keys)]
        if not members:
            return 0
        return int(self.key.rpush(*members))

    def claim(self) -> QueuedKey | None:
        key = self.key.lpop()
        if key is None:
            return None
        return QueuedKey(key=str(key), score=timestamp())

    def block_claim(self, *, timeout: int = 0) -> QueuedKey | None:
        """Block until one item is available, or until timeout expires.

        timeout=0 means block indefinitely, matching Redis BLPOP semantics.
        Use a small positive timeout when the caller needs periodic shutdown
        checks.
        """
        item = self.key.blpop(timeout=timeout)
        if item is None:
            return None

        _queue_key, value = item
        return QueuedKey(key=str(value), score=timestamp())

    def peek(self) -> QueuedKey | None:
        key = self.key.lindex(0)
        if key is None:
            return None
        return QueuedKey(key=str(key), score=timestamp())

    def count(self) -> int:
        return int(self.key.llen())

    def clear(self) -> int:
        return int(self.delete())

    # Compatibility aliases. Prefer insert()/claim()/block_claim() in new code.
    def enqueue(self, key: str, *, score: float | None = None) -> int:
        return self.insert(key, score=score)

    def enqueue_batch(
        self,
        keys: Sequence[str],
        *,
        start_score: float | None = None,
        step: float = 0.001,
    ) -> int:
        return self.insert_many(keys, start_score=start_score, step=step)

    def claim_next(self) -> QueuedKey | None:
        return self.claim()

    def block_claim_next(self, *, timeout: int = 0) -> QueuedKey | None:
        return self.block_claim(timeout=timeout)

    def peek_next(self) -> QueuedKey | None:
        return self.peek()


def insert(queue: RedisQueue, key: str, *, score: float | None = None) -> int:
    return queue.insert(key, score=score)


def insert_many(
    queue: RedisQueue,
    keys: Sequence[str],
    *,
    start_score: float | None = None,
    step: float = 0.001,
) -> int:
    return queue.insert_many(keys, start_score=start_score, step=step)


def claim(queue: RedisQueue) -> QueuedKey | None:
    return queue.claim()


def block_claim(queue: RedisQueue, *, timeout: int = 0) -> QueuedKey | None:
    return queue.block_claim(timeout=timeout)


def peek(queue: RedisQueue) -> QueuedKey | None:
    return queue.peek()


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
    "require_queue_key",
]
