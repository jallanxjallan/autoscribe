from __future__ import annotations

from typing import ClassVar, Literal, overload

from asc.redis.index_base import FixedRedisHashIndex


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


class SlugMap(FixedRedisHashIndex):
    """Global slug -> full Redis key map."""

    KEY: ClassVar[str] = SLUGMAP_KEY

    def set(self, slug: str, key: str) -> str:
        normalized_slug = _require_slug(slug)
        normalized_key = _require_key(key)
        self.key.hset(normalized_slug, normalized_key)
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
    "SlugMap",
    "clear",
    "delete",
    "get",
    "has",
    "list",
    "set",
    "slugmap_hash_key",
]