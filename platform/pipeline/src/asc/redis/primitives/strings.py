"""Redis string primitives."""

from typing import Any

from asc.redis.key import RedisKey


def get(key: RedisKey) -> str | None:
    value: Any = key._r().get(key.raw_key)
    return None if value is None else str(value)


def set(key: RedisKey, value: str) -> None:
    if not isinstance(value, str):
        raise TypeError("set() requires a string value")

    key._r().set(key.raw_key, value)


__all__ = [
    "get",
    "set",
]
