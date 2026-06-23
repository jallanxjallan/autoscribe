"""Handle worker response notices.

A worker response key is a normal orchestrator inbox message. The worker has
already saved the response record. This handler acknowledges the notice and
returns cleanly; later routing will insert it into the step index and schedule
the next operation.
"""

from asc.redis.key import RedisKey


def handle(key: RedisKey) -> bool:
    """Acknowledge a worker response result without crashing the daemon."""

    print(f"orchestrator worker_response_key={key.raw_key}")
    return True


__all__ = ["handle"]
