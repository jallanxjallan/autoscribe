"""Redis HASH primitives."""

from typing import Any

from asc.redis.key import RedisKey


def hget(key: RedisKey, field: str) -> str | None:
    value: Any = key._r().hget(key.raw_key, field)
    return None if value is None else str(value)


def hgetall(key: RedisKey) -> dict[str, str]:
    raw: Any = key._r().hgetall(key.raw_key)
    return {str(field): str(value) for field, value in dict(raw).items()}


def hkeys(key: RedisKey) -> list[str]:
    raw: Any = key._r().hkeys(key.raw_key)
    return [str(item) for item in raw]


def hlen(key: RedisKey) -> int:
    result: Any = key._r().hlen(key.raw_key)
    return int(result)


def hset(
    key: RedisKey,
    *,
    field: str | None = None,
    value: str | None = None,
    mapping: dict[str, str] | None = None,
) -> int:
    if mapping is not None:
        if field is not None or value is not None:
            raise TypeError("hset() accepts mapping or field+value, not both")
        if not mapping:
            raise ValueError("hset() mapping must be non-empty")
        for map_field, map_value in mapping.items():
            if not isinstance(map_field, str) or not isinstance(map_value, str):
                raise TypeError("hset() mapping keys and values must be strings")

        result: Any = key._r().hset(key.raw_key, mapping=mapping)
        return int(result)

    if field is None or value is None:
        raise TypeError("hset() requires either field+value or mapping")
    if not isinstance(field, str) or not isinstance(value, str):
        raise TypeError("hset() field and value must be strings")

    result: Any = key._r().hset(key.raw_key, field, value)
    return int(result)


def hdel(key: RedisKey, *fields: str) -> int:
    result: Any = key._r().hdel(key.raw_key, *fields)
    return int(result)


__all__ = [
    "hdel",
    "hget",
    "hgetall",
    "hkeys",
    "hlen",
    "hset",
]
