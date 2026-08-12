# v2/store/redis.py
import redis
from typing import Optional

_redis: Optional[redis.Redis] = None

# Redis in AutoScribe is ephemeral and schema-bound.
# Any WRONGTYPE or contract violation is a developer error.
# Fail fast. Never auto-repair.


def get_client() -> redis.Redis:
    """
    Late-bound Redis client.
    Safe for offline startup; connection is lazy.
    """
    global _redis
    if _redis is None:
        _redis = redis.Redis(decode_responses=True)
    return _redis


def pipeline():
    """
    Explicit transactional pipeline.
    """
    return get_client().pipeline(transaction=True)
