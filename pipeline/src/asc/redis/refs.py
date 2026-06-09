from __future__ import annotations

from asc.redis.key import RedisKey


def redis_key(kind: str, slug: str, *segments: str) -> str:
    """Compatibility helper for legacy callers that build concrete keys."""

    return str(RedisKey.from_parts(kind, slug, *segments))


def key_exists(kind: str, slug: str) -> bool:
    return RedisKey(redis_key(kind, slug)).exists()


def require_key(kind: str, slug: str) -> None:
    key = redis_key(kind, slug)
    if not RedisKey(key).exists():
        raise ValueError(f"missing referenced {kind} key: {key}")


def require_instruction(slug: str) -> None:
    require_key("instruction", slug)


def require_driver(slug: str) -> None:
    require_key("driver", slug)


def require_job(slug: str) -> None:
    require_key("job", slug)
