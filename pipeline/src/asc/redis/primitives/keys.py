"""Redis key-level primitives."""

from typing import Any

from asc.redis.key import RedisKey


def exists(key: RedisKey) -> bool:
    result: Any = key._r().exists(key.raw_key)
    return bool(result)


def delete(key: RedisKey) -> int:
    result: Any = key._r().delete(key.raw_key)
    return int(result)


def type(key: RedisKey) -> str:
    result: Any = key._r().type(key.raw_key)
    return str(result)


def ttl(key: RedisKey) -> int:
    result: Any = key._r().ttl(key.raw_key)
    return int(result)


def expire(key: RedisKey, seconds: int) -> bool:
    if not isinstance(seconds, int) or seconds < 0:
        raise ValueError("expire() requires non-negative int seconds")

    result: Any = key._r().expire(key.raw_key, seconds)
    return bool(result)


__all__ = [
    "delete",
    "exists",
    "expire",
    "ttl",
    "type",
]
