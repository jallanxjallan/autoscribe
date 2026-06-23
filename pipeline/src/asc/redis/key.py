from typing import ClassVar


SEP = ":"
MIN_PARTS = 2


class RedisKey:
    """Validated AutoScribe Redis key value object.

    Canonical shape:

        kind:identity[:suffix...]

    RedisKey owns the Redis client access point, but not Redis command
    primitives. Hash/list/zset helpers belong in the modules that use them.
    """

    SEP: ClassVar[str] = SEP
    MIN_PARTS: ClassVar[int] = MIN_PARTS

    def __init__(self, raw_key: str) -> None:
        if not isinstance(raw_key, str):
            raise TypeError("RedisKey requires a string")

        raw_key = raw_key.strip()
        parts = tuple(raw_key.split(self.SEP))

        if len(parts) < self.MIN_PARTS:
            raise ValueError("Redis keys must have at least kind and identity segments")

        for index, part in enumerate(parts, start=1):
            if not part:
                raise ValueError(f"Redis key segment {index} must be non-empty")
            if part != part.strip():
                raise ValueError(
                    f"Redis key segment {index} has surrounding whitespace"
                )

        self.raw_key = raw_key
        self.parts = parts

    @classmethod
    def from_parts(cls, *parts: str | None) -> "RedisKey":
        clean_parts = tuple(part for part in parts if part is not None)

        if len(clean_parts) < MIN_PARTS:
            raise ValueError("Redis keys must have at least kind and identity segments")

        for index, part in enumerate(clean_parts, start=1):
            if not isinstance(part, str):
                raise TypeError(f"Redis key segment {index} must be a string")
            if not part.strip():
                raise ValueError(f"Redis key segment {index} must be non-empty")
            if part != part.strip():
                raise ValueError(
                    f"Redis key segment {index} has surrounding whitespace"
                )
            if SEP in part:
                raise ValueError(f"Redis key segment {index} must not contain {SEP!r}")

        return cls(SEP.join(clean_parts))

    @property
    def kind(self) -> str:
        return self.parts[0]

    @property
    def identity(self) -> str:
        return self.parts[1]

    @property
    def segments(self) -> tuple[str, ...]:
        return self.parts[2:]

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


__all__ = ["MIN_PARTS", "SEP", "RedisKey"]
