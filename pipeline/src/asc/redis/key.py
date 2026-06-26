from typing import ClassVar


SEP = ":"
MIN_PARTS = 2


class RedisKey:
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


__all__ = ["MIN_PARTS", "SEP", "RedisKey"]
