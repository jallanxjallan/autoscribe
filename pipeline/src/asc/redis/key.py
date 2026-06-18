from __future__ import annotations

from typing import Any, ClassVar


SEP = ":"
MIN_PARTS = 2


def build_key(*parts: str) -> str:
    """
    Build an AutoScribe Redis key.

    Redis keys must be shaped as:

        kind:identity[:suffix...]

    The first segment is the canonical model/control kind.
    The second segment is the shared identity.
    Any remaining segments are suffix/detail segments owned by the caller.
    """

    if len(parts) < MIN_PARTS:
        raise ValueError("Redis keys must have at least kind and identity segments")

    normalized: list[str] = []

    for index, value in enumerate(parts, start=1):
        if not isinstance(value, str):
            raise TypeError(f"key segment {index} must be a str")

        value = value.strip()
        if not value:
            raise ValueError(f"key segment {index} must be non-empty")

        if SEP in value:
            raise ValueError(f"key segment {index} must not contain {SEP!r}")

        normalized.append(value)

    return SEP.join(normalized)


class RedisKey:
    """Validated Redis key wrapper.

    Supports both construction styles:

        RedisKey("kind:identity:suffix")
        RedisKey(kind="kind", identity="identity", suffix="suffix")

    The canonical shape is:

        kind:identity[:suffix...]
    """

    SEP: ClassVar[str] = SEP
    MIN_PARTS: ClassVar[int] = MIN_PARTS

    def __init__(
        self,
        key: str | None = None,
        *,
        kind: str | None = None,
        identity: str | None = None,
        suffix: str | tuple[str, ...] | list[str] | None = None,
    ) -> None:
        key_text = self._make_key(
            key=key,
            kind=kind,
            identity=identity,
            suffix=suffix,
        )
        self._validate_key(key_text)
        self.key = key_text

    @classmethod
    def from_parts(cls, *parts: str) -> RedisKey:
        return cls(build_key(*parts))

    @classmethod
    def _make_key(
        cls,
        *,
        key: str | None,
        kind: str | None,
        identity: str | None,
        suffix: str | tuple[str, ...] | list[str] | None,
    ) -> str:
        if key is not None:
            if kind is not None or identity is not None or suffix is not None:
                raise TypeError(
                    "RedisKey accepts either a full key or kind/identity/suffix, not both"
                )

            if not isinstance(key, str):
                raise TypeError("key must be a str")

            return key.strip()

        if kind is None or identity is None:
            raise TypeError("RedisKey keyword construction requires kind and identity")

        parts: list[str] = [kind, identity]

        if suffix is None:
            pass
        elif isinstance(suffix, str):
            suffix = suffix.strip()
            if suffix:
                parts.extend(suffix.split(cls.SEP))
        elif isinstance(suffix, (tuple, list)):
            parts.extend(suffix)
        else:
            raise TypeError("suffix must be a str, tuple[str, ...], list[str], or None")

        return build_key(*parts)

    @classmethod
    def _validate_key(cls, key: str) -> None:
        if not isinstance(key, str):
            raise TypeError("key must be a str")

        if len(key) < 3:
            raise ValueError("key must contain at least 3 characters")

        parts = tuple(key.split(cls.SEP))

        if len(parts) < cls.MIN_PARTS:
            raise ValueError(
                f"Invalid Redis key {key!r}; expected at least "
                f"kind and identity segments separated by {cls.SEP!r}"
            )

        for index, part in enumerate(parts, start=1):
            if not part:
                raise ValueError(
                    f"Invalid Redis key {key!r}; segment {index} is empty"
                )

            if part != part.strip():
                raise ValueError(
                    f"Invalid Redis key {key!r}; "
                    f"segment {index} has surrounding whitespace"
                )

    @property
    def parts(self) -> tuple[str, ...]:
        return tuple(self.key.split(self.SEP))

    @property
    def kind(self) -> str:
        """Canonical model selector: the first Redis key segment."""

        return self.parts[0]

    @property
    def identity(self) -> str:
        """Shared process/object identity: the second Redis key segment."""

        return self.parts[1]

    @property
    def suffix(self) -> str:
        """Remaining key detail after kind and identity, or an empty string."""

        return self.SEP.join(self.parts[2:])

    @property
    def segments(self) -> tuple[str, ...]:
        """Suffix segments after kind and identity."""

        return self.parts[2:]

    @property
    def namespace(self) -> str:
        """Compatibility alias for kind."""

        return self.kind

    @property
    def domain(self) -> str:
        """Compatibility alias for kind."""

        return self.kind

    @property
    def classifier(self) -> str | None:
        """Compatibility alias for the first suffix segment."""

        return self.segments[0] if self.segments else None

    def __str__(self) -> str:
        return self.key

    def __repr__(self) -> str:
        return f"RedisKey({self.key!r})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, RedisKey):
            return self.key == other.key

        if isinstance(other, str):
            return self.key == other

        return False

    def __hash__(self) -> int:
        return hash(self.key)

    def _r(self) -> Any:
        from asc.redis.client import get_client

        return get_client()

    def exists(self) -> bool:
        return bool(self._r().exists(self.key))

    def delete(self) -> int:
        return int(self._r().delete(self.key))

    def type(self) -> str:
        return str(self._r().type(self.key))

    def ttl(self) -> int:
        return int(self._r().ttl(self.key))

    def expire(self, seconds: int) -> bool:
        if not isinstance(seconds, int) or seconds < 0:
            raise ValueError("expire() requires non-negative int seconds")

        return bool(self._r().expire(self.key, seconds))

    # Raw string helpers are intentionally minimal.
    # Process records should use hashes.

    def get(self) -> str | None:
        return self._r().get(self.key)

    def set(self, value: str) -> None:
        if not isinstance(value, str):
            raise TypeError("set() requires a string value")

        self._r().set(self.key, value)

    # Redis HASH helpers.

    def hget(self, field: str) -> str | None:
        return self._r().hget(self.key, field)

    def hgetall(self) -> dict[str, str]:
        return dict(self._r().hgetall(self.key))

    def hkeys(self) -> list[str]:
        return [str(item) for item in self._r().hkeys(self.key)]

    def hlen(self) -> int:
        return int(self._r().hlen(self.key))

    def hset(
        self,
        *,
        field: str | None = None,
        value: str | None = None,
        mapping: dict[str, str] | None = None,
    ) -> int:
        if mapping is not None:
            return int(self._r().hset(self.key, mapping=mapping))

        if field is None or value is None:
            raise TypeError("hset() requires either field+value or mapping")

        return int(self._r().hset(self.key, field, value))

    def hdel(self, *fields: str) -> int:
        return int(self._r().hdel(self.key, *fields))

    # Redis LIST helpers.
    # Live handoff queues use RPUSH + LPOP/BLPOP.

    def rpush(self, *values: str) -> int:
        if not values:
            raise ValueError("rpush() requires at least one value")

        for value in values:
            if not isinstance(value, str):
                raise TypeError("rpush() values must be strings")

        return int(self._r().rpush(self.key, *values))

    def lpush(self, *values: str) -> int:
        if not values:
            raise ValueError("lpush() requires at least one value")

        for value in values:
            if not isinstance(value, str):
                raise TypeError("lpush() values must be strings")

        return int(self._r().lpush(self.key, *values))

    def lpop(self) -> str | None:
        value = self._r().lpop(self.key)
        return None if value is None else str(value)

    def blpop(self, *, timeout: int = 0) -> tuple[str, str] | None:
        if not isinstance(timeout, int) or timeout < 0:
            raise ValueError("blpop() timeout must be a non-negative int")

        item = self._r().blpop(self.key, timeout=timeout)
        if item is None:
            return None

        key, value = item
        return str(key), str(value)

    def lindex(self, index: int) -> str | None:
        value = self._r().lindex(self.key, index)
        return None if value is None else str(value)

    def llen(self) -> int:
        return int(self._r().llen(self.key))

    # Redis SORTED SET helpers.

    def zadd(self, mapping: dict[str, float]) -> int:
        return int(self._r().zadd(self.key, mapping))

    def zcard(self) -> int:
        return int(self._r().zcard(self.key))

    def zrange(self, start: int, stop: int) -> list[str]:
        return [str(item) for item in self._r().zrange(self.key, start, stop)]

    def zpopmin(self, count: int = 1) -> list[tuple[str, float]]:
        return [
            (str(member), float(score))
            for member, score in self._r().zpopmin(self.key, count)
        ]

    def zrangebyscore(
        self,
        min_score: float,
        max_score: float,
        **kwargs: Any,
    ) -> list[Any]:
        return list(self._r().zrangebyscore(self.key, min_score, max_score, **kwargs))

    def zscore(self, member: str) -> float | None:
        value = self._r().zscore(self.key, member)
        return None if value is None else float(value)

    def zrem(self, *members: str) -> int:
        return int(self._r().zrem(self.key, *members))

    def zrevrange(self, start: int, stop: int) -> list[str]:
        return [str(item) for item in self._r().zrevrange(self.key, start, stop)]

    def zrevrangebyscore(
        self,
        max_score: float,
        min_score: float,
        **kwargs: Any,
    ) -> list[Any]:
        return list(self._r().zrevrangebyscore(self.key, max_score, min_score, **kwargs))


__all__ = [
    "MIN_PARTS",
    "SEP",
    "RedisKey",
    "build_key",
]