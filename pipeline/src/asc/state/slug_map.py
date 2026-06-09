from __future__ import annotations

from typing import Literal, overload

from asc.state.slugmap import (
    SLUGMAP_KEY,
    SlugMap,
    bind_key,
    has_slug,
    resolve_key,
    slugmap_hash_key,
)


@overload
def resolve_identity(slug: str, *, require: Literal[True]) -> str: ...


@overload
def resolve_identity(slug: str, *, require: Literal[False] = False) -> str | None: ...


def resolve_identity(slug: str, *, require: bool = False) -> str | None:
    """Compatibility alias.

    The slugmap now stores full Redis keys, not bare identities. Legacy callers
    using resolve_identity() receive that full key.
    """

    return resolve_key(slug, require=require)


def bind_slug(slug: str, identity: str, *, overwrite: bool = False) -> str:
    """Compatibility alias for the old identity-only slug map.

    The value must now be a valid full Redis key.
    """

    return bind_key(slug, identity, overwrite=overwrite)


__all__ = [
    "SLUGMAP_KEY",
    "SlugMap",
    "bind_key",
    "bind_slug",
    "has_slug",
    "resolve_identity",
    "resolve_key",
    "slugmap_hash_key",
]
