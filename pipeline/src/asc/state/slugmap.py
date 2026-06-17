from typing import ClassVar, Literal, overload

from asc.redis.index_base import FixedRedisHashIndex
from asc.redis.key import RedisKey


SLUGMAP_KEY = "state:slugmap"


def _require_slug(value: object, *, field_name: str = "slug") -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")

    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} must be non-empty")

    return text


def _require_key(value: object, *, field_name: str = "key") -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")

    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} must be non-empty")
    if ":" not in text:
        raise ValueError(f"{field_name} must be a full Redis key, not a bare identity")

    return text


def _key_kind(key: str) -> str:
    return _require_key(key).split(":")[0]


def _key_identity(key: str) -> str:
    parts = _require_key(key).split(":")
    if len(parts) != 3 or not all(parts):
        raise ValueError(f"invalid Redis model key: {key}")
    return parts[1]


class SlugMap(FixedRedisHashIndex):
    """Global slug -> full Redis key map."""

    KEY: ClassVar[str] = SLUGMAP_KEY

    def set(self, slug: str, key: str) -> str:
        normalized_slug = _require_slug(slug)
        normalized_key = _require_key(key)
        self.key.hset(field=normalized_slug, value=normalized_key)
        return normalized_key

    @overload
    def get(self, slug: str, *, require: Literal[True]) -> str: ...

    @overload
    def get(self, slug: str, *, require: Literal[False] = False) -> str | None: ...

    def get(self, slug: str, *, require: bool = False) -> str | None:
        normalized_slug = _require_slug(slug)
        value = self.key.hget(normalized_slug)

        if value is None:
            if require:
                raise KeyError(f"slug not found: {normalized_slug}")
            return None

        return str(value)

    def resolve(self, value: str, *, expected_kind: str | None = None) -> str:
        reference = _require_slug(value, field_name="slug/key reference")

        if ":" in reference:
            key = _require_key(reference)
        else:
            key = self.get(reference, require=True)

        if expected_kind is not None and _key_kind(key) != expected_kind:
            raise ValueError(
                f"key kind mismatch: expected {expected_kind}, got {_key_kind(key)} ({key})"
            )

        if not RedisKey(key).exists():
            raise KeyError(f"missing key: {key}")

        return key

    @overload
    def reverse(self, value: str, *, require: Literal[True]) -> str: ...

    @overload
    def reverse(self, value: str, *, require: Literal[False] = False) -> str | None: ...

    def reverse(self, value: str, *, require: bool = False) -> str | None:
        reference = _require_slug(value, field_name="key/identity reference")
        entries = self.list()

        for slug, key in entries.items():
            if reference == key or reference == _key_identity(key):
                return slug

        if require:
            raise KeyError(f"slug not found for key/identity: {reference}")
        return None

    def delete(self, slug: str) -> int:
        return int(self.key.hdel(_require_slug(slug)))

    def has(self, slug: str) -> bool:
        return self.get(slug) is not None

    def list(self) -> dict[str, str]:
        entries = self.key.hgetall()
        return {str(key): str(value) for key, value in sorted(entries.items())}

    def clear(self) -> int:
        return int(super().delete())


_SLUGMAP = SlugMap()


class SlugKeyResolver:
    """Resolve source slugs or full keys into full Redis keys."""

    def __init__(self, slugmap: SlugMap | None = None) -> None:
        self._slugmap = slugmap or _SLUGMAP

    def resolve(self, value: str, expected_kind: str | None = None) -> str:
        return self._slugmap.resolve(value, expected_kind=expected_kind)

    def reverse(self, value: str, *, require: bool = False) -> str | None:
        return self._slugmap.reverse(value, require=require)


def slugmap_hash_key() -> str:
    return SLUGMAP_KEY


def set(slug: str, key: str) -> str:
    return _SLUGMAP.set(slug, key)


@overload
def get(slug: str, *, require: Literal[True]) -> str: ...


@overload
def get(slug: str, *, require: Literal[False] = False) -> str | None: ...


def get(slug: str, *, require: bool = False) -> str | None:
    return _SLUGMAP.get(slug, require=require)


def resolve(value: str, *, expected_kind: str | None = None) -> str:
    return _SLUGMAP.resolve(value, expected_kind=expected_kind)


@overload
def reverse(value: str, *, require: Literal[True]) -> str: ...


@overload
def reverse(value: str, *, require: Literal[False] = False) -> str | None: ...


def reverse(value: str, *, require: bool = False) -> str | None:
    return _SLUGMAP.reverse(value, require=require)


def delete(slug: str) -> int:
    return _SLUGMAP.delete(slug)


def has(slug: str) -> bool:
    return _SLUGMAP.has(slug)


def list() -> dict[str, str]:
    return _SLUGMAP.list()


def clear() -> int:
    return _SLUGMAP.clear()


__all__ = [
    "SLUGMAP_KEY",
    "SlugKeyResolver",
    "SlugMap",
    "clear",
    "delete",
    "get",
    "has",
    "list",
    "resolve",
    "reverse",
    "set",
    "slugmap_hash_key",
]