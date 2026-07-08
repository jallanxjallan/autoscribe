"""Redis LIST primitives."""

from typing import Any

from asc.redis.key import RedisKey


def rpush(key: RedisKey, *values: str) -> int:
    if not values:
        raise ValueError("rpush() requires at least one value")
    for value in values:
        if not isinstance(value, str):
            raise TypeError("rpush() values must be strings")

    result: Any = key._r().rpush(key.raw_key, *values)
    return int(result)


def lpush(key: RedisKey, *values: str) -> int:
    if not values:
        raise ValueError("lpush() requires at least one value")
    for value in values:
        if not isinstance(value, str):
            raise TypeError("lpush() values must be strings")

    result: Any = key._r().lpush(key.raw_key, *values)
    return int(result)


def lpop(key: RedisKey) -> str | None:
    value: Any = key._r().lpop(key.raw_key)
    return None if value is None else str(value)


def blpop(key: RedisKey, *, timeout: int = 0) -> tuple[str, str] | None:
    if not isinstance(timeout, int) or timeout < 0:
        raise ValueError("blpop() timeout must be a non-negative int")

    item: Any = key._r().blpop(key.raw_key, timeout=timeout)
    if item is None:
        return None

    raw_key, value = item
    return str(raw_key), str(value)


def lindex(key: RedisKey, index: int) -> str | None:
    value: Any = key._r().lindex(key.raw_key, index)
    return None if value is None else str(value)


def llen(key: RedisKey) -> int:
    result: Any = key._r().llen(key.raw_key)
    return int(result)


__all__ = [
    "blpop",
    "lindex",
    "llen",
    "lpop",
    "lpush",
    "rpush",
]
