"""Version indexes for published plans and instructions."""

from __future__ import annotations

from asc.core.identity import validate_ulid
from asc.redis.key import RedisKey


def _index_key(kind: str, slug: str) -> RedisKey:
    clean_kind = str(kind).strip()
    clean_slug = str(slug).strip()
    if clean_kind not in {"plan", "instruction"}:
        raise ValueError(f"unsupported publication kind: {kind}")
    if not clean_slug:
        raise ValueError("publication slug must be non-empty")
    return RedisKey(kind="publication", identity=clean_kind, segments=(clean_slug, "index"))


def bind(*, kind: str, slug: str, publication_ulid: str, record_key: str) -> str:
    validate_ulid(publication_ulid)
    key = _index_key(kind, slug)
    key.hset(field=publication_ulid, value=record_key)
    return record_key


def resolve(
    *,
    kind: str,
    slug: str,
    publication_ulid: str | None = None,
) -> tuple[str, str]:
    """Resolve the newest available version at or before publication_ulid."""

    if publication_ulid is not None:
        validate_ulid(publication_ulid)
    index = _index_key(kind, slug)
    entries = index.hgetall()
    if not entries:
        raise KeyError(f"no published {kind} versions for slug: {slug}")

    stale: list[str] = []
    eligible: list[tuple[str, str]] = []
    for version, record_key in entries.items():
        if not RedisKey(record_key).exists():
            stale.append(version)
            continue
        if publication_ulid is None or version <= publication_ulid:
            eligible.append((version, record_key))
    if stale:
        index.hdel(*stale)
    if not eligible:
        target = publication_ulid or "latest"
        raise KeyError(f"no published {kind} version for {slug} at or before {target}")
    return max(eligible, key=lambda item: item[0])


__all__ = ["bind", "resolve"]
