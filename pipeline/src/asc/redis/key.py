from typing import Any, ClassVar


SEP = ":"
MIN_PARTS = 2


class RedisKeyCommandsMixin:
    def exists(self) -> bool:
        from asc.redis.primitives import keys

        return keys.exists(self)

    def delete(self) -> int:
        from asc.redis.primitives import keys

        return keys.delete(self)

    def type(self) -> str:
        from asc.redis.primitives import keys

        return keys.type(self)

    def ttl(self) -> int:
        from asc.redis.primitives import keys

        return keys.ttl(self)

    def expire(self, seconds: int) -> bool:
        from asc.redis.primitives import keys

        return keys.expire(self, seconds)


class RedisStringCommandsMixin:
    def get(self) -> str | None:
        from asc.redis.primitives import strings

        return strings.get(self)

    def set(self, value: str) -> None:
        from asc.redis.primitives import strings

        strings.set(self, value)


class RedisHashCommandsMixin:
    def hget(self, field: str) -> str | None:
        from asc.redis.primitives import hashes

        return hashes.hget(self, field)

    def hgetall(self) -> dict[str, str]:
        from asc.redis.primitives import hashes

        return hashes.hgetall(self)

    def hkeys(self) -> list[str]:
        from asc.redis.primitives import hashes

        return hashes.hkeys(self)

    def hlen(self) -> int:
        from asc.redis.primitives import hashes

        return hashes.hlen(self)

    def hset(
        self,
        field: str | None = None,
        value: str | None = None,
        *,
        mapping: dict[str, str] | None = None,
    ) -> int:
        from asc.redis.primitives import hashes

        return hashes.hset(self, field=field, value=value, mapping=mapping)

    def hdel(self, *fields: str) -> int:
        from asc.redis.primitives import hashes

        return hashes.hdel(self, *fields)


class RedisListCommandsMixin:
    def rpush(self, *values: str) -> int:
        from asc.redis.primitives import lists

        return lists.rpush(self, *values)

    def lpush(self, *values: str) -> int:
        from asc.redis.primitives import lists

        return lists.lpush(self, *values)

    def lpop(self) -> str | None:
        from asc.redis.primitives import lists

        return lists.lpop(self)

    def blpop(self, *, timeout: int = 0) -> tuple[str, str] | None:
        from asc.redis.primitives import lists

        return lists.blpop(self, timeout=timeout)

    def lindex(self, index: int) -> str | None:
        from asc.redis.primitives import lists

        return lists.lindex(self, index)

    def llen(self) -> int:
        from asc.redis.primitives import lists

        return lists.llen(self)


class RedisSortedSetCommandsMixin:
    def zadd(self, mapping: dict[str, float]) -> int:
        from asc.redis.primitives import zsets

        return zsets.zadd(self, mapping)

    def zcard(self) -> int:
        from asc.redis.primitives import zsets

        return zsets.zcard(self)

    def zrange(self, start: int, stop: int) -> list[str]:
        from asc.redis.primitives import zsets

        return zsets.zrange(self, start, stop)

    def zpopmin(self, count: int = 1) -> list[tuple[str, float]]:
        from asc.redis.primitives import zsets

        return zsets.zpopmin(self, count)

    def zrangebyscore(
        self,
        min_score: float,
        max_score: float,
        **kwargs: Any,
    ) -> list[Any]:
        from asc.redis.primitives import zsets

        return zsets.zrangebyscore(self, min_score, max_score, **kwargs)

    def zscore(self, member: str) -> float | None:
        from asc.redis.primitives import zsets

        return zsets.zscore(self, member)

    def zrem(self, *members: str) -> int:
        from asc.redis.primitives import zsets

        return zsets.zrem(self, *members)

    def zrevrange(self, start: int, stop: int) -> list[str]:
        from asc.redis.primitives import zsets

        return zsets.zrevrange(self, start, stop)

    def zrevrangebyscore(
        self,
        max_score: float,
        min_score: float,
        **kwargs: Any,
    ) -> list[Any]:
        from asc.redis.primitives import zsets

        return zsets.zrevrangebyscore(self, max_score, min_score, **kwargs)


class RedisKey(
    RedisKeyCommandsMixin,
    RedisStringCommandsMixin,
    RedisHashCommandsMixin,
    RedisListCommandsMixin,
    RedisSortedSetCommandsMixin,
):
    """Validated AutoScribe Redis key value object.

    Canonical shape:

        kind:identity[:suffix...]

    Construction supports either a complete raw key string:

        RedisKey("call:01ABC:record")

    or labelled key parts:

        RedisKey(kind="call", identity="01ABC")
        RedisKey(kind="call", identity="01ABC", suffix="record")
        RedisKey(kind="call", identity="01ABC", segments=("record",))

    The suffix/segments are optional. Two-segment keys are first-class keys,
    not a special case.
    """

    SEP: ClassVar[str] = SEP
    MIN_PARTS: ClassVar[int] = MIN_PARTS

    def __init__(
        self,
        raw_key: str | None = None,
        *,
        kind: str | None = None,
        identity: str | None = None,
        suffix: str | int | None = None,
        segments: tuple[str | int | None, ...] | list[str | int | None] | None = None,
    ) -> None:
        if raw_key is not None and (kind is not None or identity is not None):
            raise ValueError("RedisKey accepts either raw_key or labelled parts, not both")

        if raw_key is None:
            raw_key = self._raw_from_labelled_parts(
                kind=kind,
                identity=identity,
                suffix=suffix,
                segments=segments,
            )

        if not isinstance(raw_key, str):
            raise TypeError("RedisKey requires a string")

        raw_key = raw_key.strip()
        parts = tuple(raw_key.split(self.SEP))

        self._validate_parts(parts)

        self.raw_key = raw_key
        self.parts = parts

    @classmethod
    def from_parts(cls, *parts: str | int | None) -> "RedisKey":
        clean_parts = tuple(str(part) for part in parts if part is not None)
        cls._validate_parts(clean_parts)
        return cls(SEP.join(clean_parts))

    @classmethod
    def _raw_from_labelled_parts(
        cls,
        *,
        kind: str | None,
        identity: str | None,
        suffix: str | int | None,
        segments: tuple[str | int | None, ...] | list[str | int | None] | None,
    ) -> str:
        if kind is None:
            raise ValueError("RedisKey labelled construction requires kind")
        if identity is None:
            raise ValueError("RedisKey labelled construction requires identity")

        if suffix is not None and segments is not None:
            raise ValueError("RedisKey accepts suffix or segments, not both")

        if segments is None:
            extra_parts: tuple[str, ...] = (str(suffix),) if suffix is not None else ()
        else:
            extra_parts = tuple(str(part) for part in segments if part is not None)

        return SEP.join((kind, identity, *extra_parts))

    @classmethod
    def _validate_parts(cls, parts: tuple[str, ...]) -> None:
        if len(parts) < cls.MIN_PARTS:
            raise ValueError("Redis keys must have at least kind and identity segments")

        for index, part in enumerate(parts, start=1):
            if not isinstance(part, str):
                raise TypeError(f"Redis key segment {index} must be a string")
            if not part:
                raise ValueError(f"Redis key segment {index} must be non-empty")
            if part != part.strip():
                raise ValueError(
                    f"Redis key segment {index} has surrounding whitespace"
                )
            if cls.SEP in part:
                raise ValueError(
                    f"Redis key segment {index} must not contain {cls.SEP!r}"
                )

    @property
    def kind(self) -> str:
        return self.parts[0]

    @property
    def identity(self) -> str:
        return self.parts[1]

    @property
    def segments(self) -> tuple[str, ...]:
        return self.parts[2:]

    @property
    def suffix(self) -> str | None:
        if not self.segments:
            return None
        return self.SEP.join(self.segments)

    def _r(self):
        from asc.redis.client import get_client

        return get_client()

    def __str__(self) -> str:
        return self.raw_key

    def __repr__(self) -> str:
        return f"RedisKey({self.raw_key!r})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, RedisKey):
            return self.raw_key == other.raw_key
        if isinstance(other, str):
            return self.raw_key == other
        return False

    def __hash__(self) -> int:
        return hash(self.raw_key)


__all__ = [
    "MIN_PARTS",
    "SEP",
    "RedisHashCommandsMixin",
    "RedisKey",
    "RedisKeyCommandsMixin",
    "RedisListCommandsMixin",
    "RedisSortedSetCommandsMixin",
    "RedisStringCommandsMixin",
]
