from __future__ import annotations

from typing import Literal, overload

from asc.redis.index_base import FixedRedisHashIndex
from asc.redis.key_builder import build_key


STATE_NAMESPACE = "state"
CONTROL_DOMAIN = STATE_NAMESPACE  # compatibility alias
SLUGMAP_SEGMENT = "slugmap"
SLUGMAP_KIND = SLUGMAP_SEGMENT  # compatibility alias
SLUGMAP_IDENTITY = "global"


def _require_single_segment(value: object, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    value = value.strip()
    if not value:
        raise ValueError(f"{field_name} must be a non-empty string")
    if ":" in value:
        raise ValueError(f"{field_name} must not contain ':'")
    return value


class SlugMap(FixedRedisHashIndex):
    KEY = build_key(STATE_NAMESPACE, SLUGMAP_IDENTITY, SLUGMAP_SEGMENT)

    @overload
    def resolve_identity(self, slug: str, *, require: Literal[True]) -> str: ...

    @overload
    def resolve_identity(
        self,
        slug: str,
        *,
        require: Literal[False] = False,
    ) -> str | None: ...

    def resolve_identity(self, slug: str, *, require: bool = False) -> str | None:
        slug = _require_single_segment(slug, field_name="slug")
        return self.resolve_pointer(
            slug,
            require=require,
            missing_label="slugmap",
        )

    def bind_slug(
        self,
        slug: str,
        identity: str,
        *,
        overwrite: bool = False,
    ) -> str:
        slug = _require_single_segment(slug, field_name="slug")
        identity = _require_single_segment(identity, field_name="identity")
        return self.bind_pointer(
            slug,
            identity,
            overwrite=overwrite,
            collision_label="slug",
        )

    def has_slug(self, slug: str) -> bool:
        slug = _require_single_segment(slug, field_name="slug")
        return self.has_pointer(slug)


_SLUGMAP = SlugMap()


def slugmap_hash_key() -> str:
    return SlugMap.KEY


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


__all__ = [
    "STATE_NAMESPACE",
    "CONTROL_DOMAIN",
    "SLUGMAP_SEGMENT",
    "SLUGMAP_KIND",
    "SLUGMAP_IDENTITY",
    "SlugMap",
    "bind_slug",
    "has_slug",
    "resolve_identity",
    "slugmap_hash_key",
]
