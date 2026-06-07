from __future__ import annotations

from dataclasses import dataclass

from asc.core.timestamp import timestamp
from asc.redis.index_base import FixedRedisIndex
from asc.redis.key import RedisKey


SCRIVENER_QUEUE_KEY = "queue:scrivener:pending"


@dataclass(frozen=True, slots=True)
class QueuedResult:
    result_key: str
    score: float

    @property
    def identity(self) -> str:
        return self.result_key


def _require_result_key(value: object, *, field_name: str = "result_key") -> str:
    if isinstance(value, RedisKey):
        text = str(value)
    elif isinstance(value, str):
        text = value.strip()
    else:
        raise TypeError(f"{field_name} must be a Redis key string")
    if not text:
        raise ValueError(f"{field_name} must be non-empty")
    RedisKey(text)
    return text


class ScrivenerQueue(FixedRedisIndex):
    """Queue of terminal runtime result/content keys awaiting SQL persistence."""

    KEY = SCRIVENER_QUEUE_KEY

    def enqueue(self, result_key: str | RedisKey, *, score: float | None = None) -> int:
        member = _require_result_key(result_key)
        normalized_score = timestamp() if score is None else float(score)
        return self.key.zadd({member: normalized_score})

    def claim_next(self) -> QueuedResult | None:
        items = self.key.zpopmin(1)
        if not items:
            return None
        member, score = items[0]
        return QueuedResult(result_key=str(member), score=float(score))

    def peek_next(self) -> str | None:
        items = self.key.zrange(0, 0)
        if not items:
            return None
        return str(items[0])

    def count(self) -> int:
        return int(self.key.zcard())

    def clear(self) -> int:
        return int(self.delete())


_QUEUE = ScrivenerQueue()


def scrivener_queue_key() -> str:
    return SCRIVENER_QUEUE_KEY


def enqueue(result_identity: str, *, score: float | None = None) -> int:
    return _QUEUE.enqueue(result_identity, score=score)


def claim_next() -> QueuedResult | None:
    return _QUEUE.claim_next()


def peek_next() -> str | None:
    return _QUEUE.peek_next()


def count() -> int:
    return _QUEUE.count()


def clear() -> int:
    return _QUEUE.clear()


__all__ = [
    "SCRIVENER_QUEUE_KEY",
    "QueuedResult",
    "ScrivenerQueue",
    "claim_next",
    "clear",
    "count",
    "enqueue",
    "peek_next",
    "scrivener_queue_key",
]
