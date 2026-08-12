from asc.redis.key import RedisKey

PASTURE_TTL_SECONDS = 60 * 60 * 24 * 30


def expire_old_key(old_key: str | None, new_key: str, *, ttl_seconds: int = PASTURE_TTL_SECONDS) -> None:
    if old_key and old_key != new_key:
        RedisKey(old_key).expire(ttl_seconds)


__all__ = ["PASTURE_TTL_SECONDS", "expire_old_key"]
