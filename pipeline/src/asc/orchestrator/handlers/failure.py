"""Handle worker failure notices.

A worker failure key is a normal orchestrator inbox message. The worker has
already saved the failure record. This handler acknowledges the notice and
returns cleanly; later routing policy can decide whether to continue, retry,
skip, or stop.
"""

from asc.redis.key import RedisKey


def handle(key: RedisKey) -> bool:
    """Acknowledge a worker failure result without crashing the daemon."""

    print(f"orchestrator worker_failure_key={key.raw_key}")
    return True


__all__ = ["handle"]
