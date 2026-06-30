"""Active-call zset helpers for the orchestrator.

The enqueuer owns call creation and inserts ``call:<identity>:record`` into the
active zset with score 0. The orchestrator treats that zset as its work queue:
read the oldest call, inspect its existing call index, dispatch at most one new
task, then bump the score so other calls can make progress.
"""

from __future__ import annotations

import time

from asc.redis.key import RedisKey
from asc.redis.primitives.zsets import zadd, zrange, zrem


ACTIVE_CALLS_KEY = RedisKey("state:active:index")


def oldest_active_call() -> str | None:
    members = zrange(ACTIVE_CALLS_KEY, 0, 0)
    if not members:
        return None
    return str(members[0]).strip() or None


def bump_active_call(call_key: str) -> None:
    zadd(ACTIVE_CALLS_KEY, {str(call_key): float(time.time())})


def remove_active_call(call_key: str) -> None:
    zrem(ACTIVE_CALLS_KEY, str(call_key))


__all__ = [
    "ACTIVE_CALLS_KEY",
    "bump_active_call",
    "oldest_active_call",
    "remove_active_call",
]
