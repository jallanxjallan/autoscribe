# asc/state/queue.py
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from asc.core.timestamp import timestamp
from asc.redis.index_base import FixedRedisIndex


@dataclass(frozen=True, slots=True)
class QueuedKey:
    """One claimed queue item.

    The aliases keep callers simple during the cursor/call_state rename.  The
    queue only knows that the member is a full Redis key; domain modules decide
    what that key points to.
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
    """Small sorted-set queue.

    Subclasses provide only KEY.  All queue behavior lives here so individual
    queue managers stay as thin wrappers.
    """

    KEY: str

    def insert(self, key: str, *, score: float | None = None) -> int:
        member = require_queue_key(key)
        queued_at = timestamp() if score is None else float(score)
        return int(self.key.zadd({member: queued_at}))

    def insert_many(
        self,
        keys: Sequence[str],
        *,
        start_score: float | None = None,
        step: float = 0.001,
    ) -> int:
        if step <= 0:
            raise ValueError("step must be > 0")
        if not keys:
            return 0

        score = timestamp() if start_score is None else float(start_score)
        mapping: dict[str, float] = {}

        for index, key in enumerate(keys):
            mapping[require_queue_key(key, field_name=f"keys[{index}]")] = score
            score += float(step)

        return int(self.key.zadd(mapping))

    def claim(self) -> QueuedKey | None:
        items = self.key.zpopmin(1)
        if not items:
            return None

        key, score = items[0]
        return QueuedKey(key=str(key), score=float(score))

    def peek(self) -> QueuedKey | None:
        items = self.key.zrange(0, 0, withscores=True)
        if not items:
            return None

        key, score = items[0]
        return QueuedKey(key=str(key), score=float(score))

    def count(self) -> int:
        return int(self.key.zcard())

    def clear(self) -> int:
        return int(self.delete())

    # Compatibility aliases.  Prefer insert()/claim() in new code.
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


def peek(queue: RedisQueue) -> QueuedKey | None:
    return queue.peek()


def count(queue: RedisQueue) -> int:
    return queue.count()


def clear(queue: RedisQueue) -> int:
    return queue.clear()


__all__ = [
    "QueuedKey",
    "RedisQueue",
    "claim",
    "clear",
    "count",
    "insert",
    "insert_many",
    "peek",
    "require_queue_key",
]
