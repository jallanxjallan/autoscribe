from __future__ import annotations

from typing import Any, ClassVar

from attr import define, field, validators

from asc.redis.client import get_client
from asc.redis.key_builder import MIN_PARTS, SEP, build_key


@define(frozen=True)
class RedisKey:
    key: str = field(
        validator=[
            validators.instance_of(str),
            validators.min_len(3),
        ]
    )

    SEP: ClassVar[str] = SEP
    MIN_PARTS: ClassVar[int] = MIN_PARTS

    def __attrs_post_init__(self) -> None:
        parts = self.parts
        if len(parts) < self.MIN_PARTS:
            raise ValueError(
                f"Invalid Redis key '{self.key}'; expected at least "
                f"namespace and identity segments separated by '{self.SEP}'"
            )
        for index, part in enumerate(parts, start=1):
            if not part:
                raise ValueError(
                    f"Invalid Redis key '{self.key}'; segment {index} is empty"
                )
            if part != part.strip():
                raise ValueError(
                    f"Invalid Redis key '{self.key}'; segment {index} has surrounding whitespace"
                )

    @property
    def parts(self) -> tuple[str, ...]:
        return tuple(self.key.split(self.SEP))

    @property
    def namespace(self) -> str:
        return self.parts[0]

    @property
    def domain(self) -> str:
        """Backward-compatible alias for namespace."""
        return self.namespace

    @property
    def identity(self) -> str:
        return self.parts[1]

    @property
    def segments(self) -> tuple[str, ...]:
        return self.parts[2:]

    @property
    def classifier(self) -> str | None:
        """Backward-compatible alias for the first extra segment."""
        return self.segments[0] if self.segments else None

    @classmethod
    def from_parts(cls, *parts: str) -> "RedisKey":
        return cls(build_key(*parts))

    def __str__(self) -> str:
        return self.key

    def _r(self) -> Any:
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

    # Raw string helpers are intentionally minimal. Runtime records should use hashes.

    def get(self) -> str | None:
        return self._r().get(self.key)

    def set(self, value: str) -> None:
        if not isinstance(value, str):
            raise TypeError("set() requires a string value")
        self._r().set(self.key, value)

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

    def zadd(self, mapping: dict[str, float]) -> int:
        return int(self._r().zadd(self.key, mapping))

    def zcard(self) -> int:
        return int(self._r().zcard(self.key))

    def zrange(self, start: int, stop: int) -> list[str]:
        return [str(item) for item in self._r().zrange(self.key, start, stop)]

    def zpopmin(self, count: int = 1) -> list[tuple[str, float]]:
        return [(str(member), float(score)) for member, score in self._r().zpopmin(self.key, count)]

    def zrangebyscore(self, min_score: float, max_score: float, **kwargs: Any) -> list[Any]:
        return list(self._r().zrangebyscore(self.key, min_score, max_score, **kwargs))

    def zscore(self, member: str) -> float | None:
        value = self._r().zscore(self.key, member)
        return None if value is None else float(value)

    def zrem(self, *members: str) -> int:
        return int(self._r().zrem(self.key, *members))

    def zrevrange(self, start: int, stop: int) -> list[str]:
        return [str(item) for item in self._r().zrevrange(self.key, start, stop)]

    def zrevrangebyscore(self, max_score: float, min_score: float, **kwargs: Any) -> list[Any]:
        return list(self._r().zrevrangebyscore(self.key, max_score, min_score, **kwargs))
