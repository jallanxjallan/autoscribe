from typing import ClassVar, Literal, overload

from asc.redis.index_base import FixedRedisHashIndex
from asc.redis.key import RedisKey


SLUGMAP_KEY = "control:slugmap:index"


def _require_text(value: object, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")

    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} must be non-empty")

    return text


def _require_slug(value: object, *, field_name: str = "slug") -> str:
    return _require_text(value, field_name=field_name)


def _require_key(value: object, *, field_name: str = "key") -> str:
    text = _require_text(value, field_name=field_name)

    if ":" not in text:
        raise ValueError(f"{field_name} must be a full Redis key, not a bare identity")

    return text


def _redis_text(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")

    if isinstance(value, str):
        return value

    raise TypeError(f"expected Redis text value, got {type(value).__name__}")


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

        return _redis_text(value)

    def resolve(self, value: str, *, expected_kind: str | None = None) -> str:
        reference = _require_slug(value, field_name="slug/key reference")

        if ":" in reference:
            key = _require_key(reference)
        else:
            key = self.get(reference, require=True)

        redis_key = RedisKey(key)

        if expected_kind is not None and redis_key.kind != expected_kind:
            raise ValueError(
                f"key kind mismatch: expected {expected_kind}, "
                f"got {redis_key.kind} ({key})"
            )

        if not redis_key.exists():
            raise KeyError(f"missing key: {key}")

        return key

    @overload
    def reverse(self, value: str, *, require: Literal[True]) -> str: ...

    @overload
    def reverse(self, value: str, *, require: Literal[False] = False) -> str | None: ...

    def reverse(self, value: str, *, require: bool = False) -> str | None:
        reference = _require_slug(value, field_name="key/identity reference")

        for slug, key in self.list_slugs().items():
            redis_key = RedisKey(key)

            if reference == key or reference == redis_key.identity:
                return slug

        if require:
            raise KeyError(f"slug not found for key/identity: {reference}")

        return None

    def delete(self, slug: str) -> int:
        return int(self.key.hdel(_require_slug(slug)))

    def has(self, slug: str) -> bool:
        return self.get(slug) is not None

    def list_slugs(self) -> dict[str, str]:
        entries = self.key.hgetall()

        return {
            _redis_text(slug): _redis_text(key)
            for slug, key in sorted(entries.items())
        }

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


def set_slug_key(slug: str, key: str) -> str:
    return _SLUGMAP.set(slug, key)


@overload
def get_slug_key(slug: str, *, require: Literal[True]) -> str: ...


@overload
def get_slug_key(slug: str, *, require: Literal[False] = False) -> str | None: ...


def get_slug_key(slug: str, *, require: bool = False) -> str | None:
    return _SLUGMAP.get(slug, require=require)


def resolve_slug_key(value: str, *, expected_kind: str | None = None) -> str:
    return _SLUGMAP.resolve(value, expected_kind=expected_kind)


@overload
def reverse_slug_key(value: str, *, require: Literal[True]) -> str: ...


@overload
def reverse_slug_key(
    value: str, *, require: Literal[False] = False
) -> str | None: ...


def reverse_slug_key(value: str, *, require: bool = False) -> str | None:
    return _SLUGMAP.reverse(value, require=require)


def delete_slug(slug: str) -> int:
    return _SLUGMAP.delete(slug)


def has_slug(slug: str) -> bool:
    return _SLUGMAP.has(slug)


def list_slugs() -> dict[str, str]:
    return _SLUGMAP.list_slugs()


def clear_slugmap() -> int:
    return _SLUGMAP.clear()


__all__ = [
    "SLUGMAP_KEY",
    "SlugKeyResolver",
    "SlugMap",
    "clear_slugmap",
    "delete_slug",
    "get_slug_key",
    "has_slug",
    "list_slugs",
    "resolve_slug_key",
    "reverse_slug_key",
    "set_slug_key",
    "slugmap_hash_key",
]