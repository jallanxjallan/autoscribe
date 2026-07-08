from dataclasses import dataclass

from asc.core.timestamp import timestamp
from asc.redis.key import RedisKey


@dataclass(frozen=True, slots=True)
class QueuedItem:
    value: str
    score: float


class RedisSortedSetQueue:
    """Small Redis zset FIFO-ish queue wrapper storing string payloads."""

    def __init__(self, key: str | RedisKey) -> None:
        self.key = key if isinstance(key, RedisKey) else RedisKey(str(key))

    @staticmethod
    def _payload(value: object, field_name: str = "queue payload") -> str:
        if isinstance(value, RedisKey):
            value = str(value)
        if not isinstance(value, str):
            raise TypeError(f"{field_name} must be a string")
        value = value.strip()
        if not value:
            raise ValueError(f"{field_name} must be non-empty")
        return value

    def enqueue(self, value: str | RedisKey, *, score: float | None = None) -> str:
        payload = self._payload(value)
        normalized_score = timestamp() if score is None else float(score)
        self.key.zadd({payload: normalized_score})
        return payload

    def claim(self) -> QueuedItem | None:
        items = self.key.zpopmin(1)
        if not items:
            return None

        value, score = items[0]
        return QueuedItem(value=str(value), score=float(score))

    def peek(self) -> str | None:
        items = self.key.zrange(0, 0)
        if not items:
            return None
        return str(items[0])

    def count(self) -> int:
        return self.key.zcard()

    def clear(self) -> int:
        return self.key.delete()


__all__ = ["QueuedItem", "RedisSortedSetQueue"]
