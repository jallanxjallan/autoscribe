from __future__ import annotations

from typing import ClassVar, Literal, overload

from asc.redis.index_base import FixedRedisHashIndex
from asc.redis.key import RedisKey
from asc.redis.model_base import RedisModel


CONTROL_SLUGMAP_TTL_SECONDS = 60 * 60 * 24 * 30


class ControlSlugMap(FixedRedisHashIndex):
    """
    Global control slug -> full Redis key map.

    Fields are globally unique slugs. Values are full Redis keys for current
    uploaded control records, for example:
        ins.tighten.prose -> control:01KS...:instruction
    """

    KEY: ClassVar[str] = "control:slugmap"

    def bind_record(
        self,
        record: RedisModel,
        *,
        full_key: str | None = None,
        ttl_seconds: int = CONTROL_SLUGMAP_TTL_SECONDS,
    ) -> str:
        slug = getattr(record, "slug", None)

        if not isinstance(slug, str) or not slug.strip():
            raise RuntimeError(f"control record is missing slug: {record!r}")

        resolved_key = full_key or str(record.redis_key)
        RedisKey(resolved_key)  # validate key shape

        # Re-uploading a slug intentionally repoints it to the newest ULID key.
        self.bind_pointer(
            slug,
            resolved_key,
            overwrite=True,
            collision_label="control slug",
        )

        RedisKey(resolved_key).expire(ttl_seconds)
        return resolved_key

    def list_bindings(self) -> dict[str, str]:
        entries = RedisKey(self.KEY).hgetall()

        if entries is None:
            return {}

        if not isinstance(entries, dict):
            raise RuntimeError(f"control slugmap must decode to dict: {self.KEY}")

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
        ttl_seconds: int = CONTROL_SLUGMAP_TTL_SECONDS,
        expected_kind: str | None = None,
    ) -> str: ...

    @overload
    def resolve_key(
        self,
        slug: str,
        *,
        require: Literal[False] = False,
        touch: bool = True,
        ttl_seconds: int = CONTROL_SLUGMAP_TTL_SECONDS,
        expected_kind: str | None = None,
    ) -> str | None: ...

    def resolve_key(
        self,
        slug: str,
        *,
        require: bool = False,
        touch: bool = True,
        ttl_seconds: int = CONTROL_SLUGMAP_TTL_SECONDS,
        expected_kind: str | None = None,
    ) -> str | None:
        full_key = self.resolve_pointer(
            slug,
            require=require,
            missing_label="control slugmap",
        )

        if full_key is None:
            return None

        target = RedisKey(full_key)

        if not target.exists():
            self.delete_pointer(slug)

            if require:
                raise KeyError(f"stale control slugmap entry for {slug}: {full_key}")

            return None

        if expected_kind is not None:
            _require_kind(target, expected_kind, label=slug)

        if touch:
            target.expire(ttl_seconds)

        return full_key


def _require_kind(key: RedisKey, expected_kind: str, *, label: str) -> None:
    expected_kind = expected_kind.strip()
    if not expected_kind:
        raise ValueError("expected_kind must be non-empty")

    actual = key.segments[-1] if key.segments else None
    if actual != expected_kind:
        raise ValueError(
            f"control key kind mismatch for {label}: expected {expected_kind}, got {actual} ({key})"
        )


__all__ = [
    "CONTROL_SLUGMAP_TTL_SECONDS",
    "ControlSlugMap",
]