from __future__ import annotations

from dataclasses import dataclass

from asc.core.timestamp import timestamp
from asc.redis.index_base import FixedRedisIndex
from asc.redis.key import RedisKey


@dataclass(frozen=True, slots=True)
class IndexedMember:
    member: str
    score: float

    @property
    def identity(self) -> str:
        return self.member


def _member(value: object, field_name: str = "member") -> str:
    if isinstance(value, RedisKey):
        text = str(value)
    elif isinstance(value, str):
        text = value.strip()
    else:
        raise TypeError(f"{field_name} must be a string")
    if not text:
        raise ValueError(f"{field_name} must be non-empty")
    return text


class ChronologyIndex(FixedRedisIndex):
    """Small sorted-set index helper for inspectable runtime chronology."""

    KEY: str

    def append(self, member: str | RedisKey, *, score: float | None = None) -> int:
        normalized = _member(member)
        normalized_score = timestamp() if score is None else float(score)
        return self.key.zadd({normalized: normalized_score})

    def score(self, member: str | RedisKey) -> float | None:
        value = self.key.zscore(_member(member))
        if value is None:
            return None
        return float(value)

    def latest(self) -> str | None:
        items = self.key.zrange(-1, -1)
        if not items:
            return None
        return str(items[0])

    def list_members(self, start: int = 0, end: int = -1, *, newest_first: bool = False) -> list[str]:
        if newest_first:
            return [str(item) for item in self.key.zrevrange(start, end)]
        return [str(item) for item in self.key.zrange(start, end)]

    def list_window(
        self,
        *,
        min_score: float,
        max_score: float,
        newest_first: bool = False,
        limit: int | None = None,
    ) -> list[IndexedMember]:
        kwargs = {"withscores": True}
        if limit is not None:
            kwargs.update({"start": 0, "num": int(limit)})
        if newest_first:
            items = self.key.zrevrangebyscore(float(max_score), float(min_score), **kwargs)
        else:
            items = self.key.zrangebyscore(float(min_score), float(max_score), **kwargs)
        return [IndexedMember(member=str(member), score=float(score)) for member, score in items]

    def count(self) -> int:
        return int(self.key.zcard())

    def clear(self) -> int:
        return int(self.delete())


__all__ = ["ChronologyIndex", "IndexedMember"]
