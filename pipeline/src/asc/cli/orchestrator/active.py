"""Active-call zset helpers for the orchestrator.

The enqueuer owns call creation and inserts ``call:<identity>:record`` into the
active zset with score 0. The orchestrator treats that zset as its work queue:
read a small visibility window, inspect a visible call, dispatch at most one new
task, then rescore the call so other calls can make progress.
"""

from __future__ import annotations

from dataclasses import dataclass
import time

from asc.redis.key import RedisKey
from asc.redis.primitives.zsets import zadd, zrange, zrem, zscore


ACTIVE_CALLS_KEY = RedisKey("state:active:index")
ACTIVE_WINDOW_LIMIT = 16
WAITING_CALL_DELAY_SECONDS = 3.0
ORCHESTRATOR_IDLE_SLEEP_SECONDS = 5.0



@dataclass(frozen=True, slots=True)
class ActiveCall:
    key: str
    score: float

    @property
    def visible(self) -> bool:
        return self.score <= time.time()


def oldest_active_call() -> str | None:
    calls = visible_active_calls(limit=1)
    if not calls:
        return None
    return calls[0].key


def active_call_window(*, limit: int = ACTIVE_WINDOW_LIMIT) -> list[ActiveCall]:
    members = zrange(ACTIVE_CALLS_KEY, 0, max(0, limit - 1))
    calls: list[ActiveCall] = []

    for member in members:
        key = str(member).strip()
        if not key:
            continue
        score = zscore(ACTIVE_CALLS_KEY, key)
        if score is None:
            continue
        calls.append(ActiveCall(key=key, score=float(score)))

    return calls


def visible_active_calls(*, limit: int = ACTIVE_WINDOW_LIMIT) -> list[ActiveCall]:
    now = time.time()
    return [call for call in active_call_window(limit=limit) if call.score <= now]


def seconds_until_next_visible(
    *,
    limit: int = ACTIVE_WINDOW_LIMIT,
    calls: list[ActiveCall] | None = None,
) -> float | None:
    current_calls = active_call_window(limit=limit) if calls is None else calls
    if not current_calls:
        return None

    delay = current_calls[0].score - time.time()
    if delay <= 0:
        return 0.0
    return min(delay, ORCHESTRATOR_IDLE_SLEEP_SECONDS)


def bump_active_call(call_key: str) -> None:
    zadd(ACTIVE_CALLS_KEY, {str(call_key): float(time.time())})


def defer_active_call(
    call_key: str,
    *,
    delay_seconds: float = WAITING_CALL_DELAY_SECONDS,
) -> None:
    zadd(ACTIVE_CALLS_KEY, {str(call_key): float(time.time()) + delay_seconds})


def remove_active_call(call_key: str) -> None:
    zrem(ACTIVE_CALLS_KEY, str(call_key))


__all__ = [
    "ACTIVE_CALLS_KEY",
    "ACTIVE_WINDOW_LIMIT",
    "ORCHESTRATOR_IDLE_SLEEP_SECONDS",
    "WAITING_CALL_DELAY_SECONDS",
    "ActiveCall",
    "active_call_window",
    "bump_active_call",
    "defer_active_call",
    "oldest_active_call",
    "remove_active_call",
    "seconds_until_next_visible",
    "visible_active_calls",
]
