from __future__ import annotations

from typing import Literal, overload

from asc.redis.index_base import FixedRedisHashIndex


SLUGMAP_KEY = "state:global:slugmap"


def _segment(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} must be non-empty")
    if ":" in text:
        raise ValueError(f"{field_name} must not contain ':'")
    return text


class SlugMap(FixedRedisHashIndex):
    KEY = SLUGMAP_KEY

    @overload
    def resolve_identity(self, slug: str, *, require: Literal[True]) -> str: ...

    @overload
    def resolve_identity(self, slug: str, *, require: Literal[False] = False) -> str | None: ...

    def resolve_identity(self, slug: str, *, require: bool = False) -> str | None:
        return self.resolve_pointer(_segment(slug, "slug"), require=require, missing_label="slugmap")

    def bind_slug(self, slug: str, identity: str, *, overwrite: bool = False) -> str:
        return self.bind_pointer(_segment(slug, "slug"), _segment(identity, "identity"), overwrite=overwrite, collision_label="slug")

    def has_slug(self, slug: str) -> bool:
        return self.has_pointer(_segment(slug, "slug"))


_SLUGMAP = SlugMap()


def slugmap_hash_key() -> str:
    return SLUGMAP_KEY


@overload
def resolve_identity(slug: str, *, require: Literal[True]) -> str: ...


@overload
def resolve_identity(slug: str, *, require: Literal[False] = False) -> str | None: ...


def resolve_identity(slug: str, *, require: bool = False) -> str | None:
    return _SLUGMAP.resolve_identity(slug, require=require)


def bind_slug(slug: str, identity: str, *, overwrite: bool = False) -> str:
    return _SLUGMAP.bind_slug(slug, identity, overwrite=overwrite)


def has_slug(slug: str) -> bool:
    return _SLUGMAP.has_slug(slug)


__all__ = ["SLUGMAP_KEY", "SlugMap", "bind_slug", "has_slug", "resolve_identity", "slugmap_hash_key"]
