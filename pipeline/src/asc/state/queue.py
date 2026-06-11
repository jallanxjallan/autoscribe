# asc/state/queue.py
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from asc.core.timestamp import timestamp
from asc.redis.index_base import FixedRedisIndex


@dataclass(frozen=True, slots=True)
class QueuedKey:
    key: str
    score: float


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
    KEY: str

    def enqueue(self, key: str, *, score: float | None = None) -> int:
        member = require_queue_key(key)
        return self.key.zadd({member: timestamp() if score is None else float(score)})

    def enqueue_batch(
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

        return self.key.zadd(mapping)

    def claim_next(self) -> QueuedKey | None:
        items = self.key.zpopmin(1)
        if not items:
            return None

        key, score = items[0]
        return QueuedKey(key=str(key), score=float(score))

    def peek_next(self) -> QueuedKey | None:
        items = self.key.zrange(0, 0, withscores=True)
        if not items:
            return None

        key, score = items[0]
        return QueuedKey(key=str(key), score=float(score))

    def count(self) -> int:
        return int(self.key.zcard())

    def clear(self) -> int:
        return int(self.delete())


__all__ = [
    "QueuedKey",
    "RedisQueue",
    "require_queue_key",
]