"""Redis SORTED SET primitives."""

from typing import Any

from asc.redis.key import RedisKey


def zadd(key: RedisKey, mapping: dict[str, float]) -> int:
    result: Any = key._r().zadd(key.raw_key, mapping)
    return int(result)


def zcard(key: RedisKey) -> int:
    result: Any = key._r().zcard(key.raw_key)
    return int(result)


def zrange(key: RedisKey, start: int, stop: int) -> list[str]:
    raw: Any = key._r().zrange(key.raw_key, start, stop)
    return [str(item) for item in raw]


def zpopmin(key: RedisKey, count: int = 1) -> list[tuple[str, float]]:
    raw: Any = key._r().zpopmin(key.raw_key, count)
    return [(str(member), float(score)) for member, score in raw]


def zrangebyscore(
    key: RedisKey,
    min_score: float,
    max_score: float,
    **kwargs: Any,
) -> list[Any]:
    raw: Any = key._r().zrangebyscore(key.raw_key, min_score, max_score, **kwargs)
    return list(raw)


def zscore(key: RedisKey, member: str) -> float | None:
    value: Any = key._r().zscore(key.raw_key, member)
    return None if value is None else float(value)


def zrem(key: RedisKey, *members: str) -> int:
    result: Any = key._r().zrem(key.raw_key, *members)
    return int(result)


def zrevrange(key: RedisKey, start: int, stop: int) -> list[str]:
    raw: Any = key._r().zrevrange(key.raw_key, start, stop)
    return [str(item) for item in raw]


def zrevrangebyscore(
    key: RedisKey,
    max_score: float,
    min_score: float,
    **kwargs: Any,
) -> list[Any]:
    raw: Any = key._r().zrevrangebyscore(key.raw_key, max_score, min_score, **kwargs)
    return list(raw)


__all__ = [
    "zadd",
    "zcard",
    "zpopmin",
    "zrange",
    "zrangebyscore",
    "zrem",
    "zrevrange",
    "zrevrangebyscore",
    "zscore",
]
