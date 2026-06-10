from __future__ import annotations

from typing import ClassVar, Literal, overload

from asc.redis.index_base import FixedRedisHashIndex
from asc.redis.key import RedisKey
from asc.redis.model_base import RedisModel


SLUGMAP_TTL_SECONDS = 60 * 60 * 24 * 30
SLUGMAP_KEY = "state:slugmap"


def _slug(value: object, field_name: str = "slug") -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} must be non-empty")
    return text


class SlugMap(FixedRedisHashIndex):
    """Global slug -> full Redis key map.

    The map is intentionally domain-neutral. It can point to current records for
    controls, plans, prompts, and any other uploaded source record whose human
    slug must resolve to the latest concrete Redis key.
    """

    KEY: ClassVar[str] = SLUGMAP_KEY

    def bind_record(
        self,
        record: RedisModel,
        *,
        full_key: str | None = None,
        ttl_seconds: int = SLUGMAP_TTL_SECONDS,
    ) -> str:
        slug = _slug(getattr(record, "slug", None))
        resolved_key = full_key or str(record.redis_key)
        RedisKey(resolved_key)  # validate key shape

        # Re-uploading a slug intentionally repoints it to the newest ULID key.
        self.bind_pointer(slug, resolved_key, overwrite=True, collision_label="slug")

        if ttl_seconds > 0:
            RedisKey(resolved_key).expire(ttl_seconds)
        return resolved_key

    def bind_key(
        self,
        slug: str,
        full_key: str | RedisKey,
        *,
        overwrite: bool = True,
        ttl_seconds: int | None = SLUGMAP_TTL_SECONDS,
    ) -> str:
        normalized_slug = _slug(slug)
        resolved_key = str(full_key)
        RedisKey(resolved_key)
        self.bind_pointer(
            normalized_slug,
            resolved_key,
            overwrite=overwrite,
            collision_label="slug",
        )
        if ttl_seconds is not None and ttl_seconds > 0:
            RedisKey(resolved_key).expire(ttl_seconds)
        return resolved_key

    # Compatibility aliases for callers that use generic index verbs.
    def bind(self, slug: str, full_key: str | RedisKey, **kwargs: object) -> str:
        return self.bind_key(slug, full_key, **kwargs)  # type: ignore[arg-type]

    def set_key(self, slug: str, full_key: str | RedisKey, **kwargs: object) -> str:
        return self.bind_key(slug, full_key, **kwargs)  # type: ignore[arg-type]

    def store(self, slug: str, full_key: str | RedisKey, **kwargs: object) -> str:
        return self.bind_key(slug, full_key, **kwargs)  # type: ignore[arg-type]

    def record(self, slug: str, full_key: str | RedisKey, **kwargs: object) -> str:
        return self.bind_key(slug, full_key, **kwargs)  # type: ignore[arg-type]

    def list_bindings(self) -> dict[str, str]:
        entries = self.key.hgetall()
        return {str(key): str(value) for key, value in sorted(entries.items())}

    def list_slugs(self) -> list[str]:
        return list(self.list_bindings())

    @overload
    def resolve_key(
        self,
        slug: str,
        *,
        require: Literal[True],
        touch: bool = True,
        ttl_seconds: int = SLUGMAP_TTL_SECONDS,
        expected_kind: str | None = None,
        expected_namespace: str | None = None,
    ) -> str: ...

    @overload
    def resolve_key(
        self,
        slug: str,
        *,
        require: Literal[False] = False,
        touch: bool = True,
        ttl_seconds: int = SLUGMAP_TTL_SECONDS,
        expected_kind: str | None = None,
        expected_namespace: str | None = None,
    ) -> str | None: ...

    def resolve_key(
        self,
        slug: str,
        *,
        require: bool = False,
        touch: bool = True,
        ttl_seconds: int = SLUGMAP_TTL_SECONDS,
        expected_kind: str | None = None,
        expected_namespace: str | None = None,
    ) -> str | None:
        normalized_slug = _slug(slug)
        full_key = self.resolve_pointer(
            normalized_slug,
            require=require,
            missing_label="slugmap",
        )

        if full_key is None:
            return None

        target = RedisKey(full_key)

        if not target.exists():
            self.delete_pointer(normalized_slug)
            if require:
                raise KeyError(f"stale slugmap entry for {normalized_slug}: {full_key}")
            return None

        if expected_namespace is not None:
            _require_namespace(target, expected_namespace, label=normalized_slug)

        if expected_kind is not None:
            _require_kind(target, expected_kind, label=normalized_slug)

        if touch and ttl_seconds > 0:
            target.expire(ttl_seconds)

        return full_key

    def has_slug(self, slug: str) -> bool:
        return self.has_pointer(_slug(slug))


def _require_namespace(key: RedisKey, expected_namespace: str, *, label: str) -> None:
    expected_namespace = expected_namespace.strip()
    if not expected_namespace:
        raise ValueError("expected_namespace must be non-empty")
    if key.namespace != expected_namespace:
        raise ValueError(
            f"slugmap namespace mismatch for {label}: "
            f"expected {expected_namespace}, got {key.namespace} ({key})"
        )


def _require_kind(key: RedisKey, expected_kind: str, *, label: str) -> None:
    expected_kind = expected_kind.strip()
    if not expected_kind:
        raise ValueError("expected_kind must be non-empty")

    actual = key.segments[-1] if key.segments else None
    if actual != expected_kind:
        raise ValueError(
            f"slugmap key kind mismatch for {label}: expected {expected_kind}, got {actual} ({key})"
        )


_SLUGMAP = SlugMap()


def slugmap_hash_key() -> str:
    return SLUGMAP_KEY


def bind_record(
    record: RedisModel,
    *,
    full_key: str | None = None,
    ttl_seconds: int = SLUGMAP_TTL_SECONDS,
) -> str:
    return _SLUGMAP.bind_record(record, full_key=full_key, ttl_seconds=ttl_seconds)


def bind_key(
    slug: str,
    full_key: str | RedisKey,
    *,
    overwrite: bool = True,
    ttl_seconds: int | None = SLUGMAP_TTL_SECONDS,
) -> str:
    return _SLUGMAP.bind_key(
        slug,
        full_key,
        overwrite=overwrite,
        ttl_seconds=ttl_seconds,
    )


def bind(slug: str, full_key: str | RedisKey, **kwargs: object) -> str:
    return bind_key(slug, full_key, **kwargs)  # type: ignore[arg-type]


def set_key(slug: str, full_key: str | RedisKey, **kwargs: object) -> str:
    return bind_key(slug, full_key, **kwargs)  # type: ignore[arg-type]


def store(slug: str, full_key: str | RedisKey, **kwargs: object) -> str:
    return bind_key(slug, full_key, **kwargs)  # type: ignore[arg-type]


def record(slug: str, full_key: str | RedisKey, **kwargs: object) -> str:
    return bind_key(slug, full_key, **kwargs)  # type: ignore[arg-type]


@overload
def resolve_key(slug: str, *, require: Literal[True], **kwargs: object) -> str: ...


@overload
def resolve_key(slug: str, *, require: Literal[False] = False, **kwargs: object) -> str | None: ...


def resolve_key(slug: str, *, require: bool = False, **kwargs: object) -> str | None:
    return _SLUGMAP.resolve_key(slug, require=require, **kwargs)


def list_bindings() -> dict[str, str]:
    return _SLUGMAP.list_bindings()


def list_slugs() -> list[str]:
    return _SLUGMAP.list_slugs()


def has_slug(slug: str) -> bool:
    return _SLUGMAP.has_slug(slug)


__all__ = [
    "SLUGMAP_KEY",
    "SLUGMAP_TTL_SECONDS",
    "SlugMap",
    "bind",
    "bind_key",
    "bind_record",
    "record",
    "set_key",
    "store",
    "has_slug",
    "list_bindings",
    "list_slugs",
    "resolve_key",
    "slugmap_hash_key",
]
