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
IDLE_SLEEP_SECONDS = 5.0
COMPLETED_CALL_DELAY_SECONDS = 365 * 24 * 60 * 60


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


def active_call_window(
    *,
    limit: int = ACTIVE_WINDOW_LIMIT,
    target_keys: set[str] | None = None,
) -> list[ActiveCall]:
    if target_keys is not None:
        calls = _target_active_calls(target_keys=target_keys)
        return calls[: max(0, limit)]

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


def _target_active_calls(*, target_keys: set[str]) -> list[ActiveCall]:
    calls: list[ActiveCall] = []

    for raw in target_keys:
        key = str(raw).strip()
        if not key:
            continue
        score = zscore(ACTIVE_CALLS_KEY, key)
        if score is None:
            continue
        calls.append(ActiveCall(key=key, score=float(score)))

    return sorted(calls, key=lambda call: call.score)


def visible_active_calls(
    *,
    limit: int = ACTIVE_WINDOW_LIMIT,
    target_keys: set[str] | None = None,
) -> list[ActiveCall]:
    now = time.time()
    return [
        call
        for call in active_call_window(limit=limit, target_keys=target_keys)
        if call.score <= now
    ]


def seconds_until_next_visible(
    *,
    limit: int = ACTIVE_WINDOW_LIMIT,
    calls: list[ActiveCall] | None = None,
    target_keys: set[str] | None = None,
) -> float | None:
    window = (
        active_call_window(limit=limit, target_keys=target_keys)
        if calls is None
        else calls
    )
    if not window:
        return None

    delay = window[0].score - time.time()
    if delay <= 0:
        return 0.0
    return min(delay, IDLE_SLEEP_SECONDS)


def bump_active_call(call_key: str) -> None:
    zadd(ACTIVE_CALLS_KEY, {str(call_key): float(time.time())})


def defer_active_call(
    call_key: str,
    *,
    delay_seconds: float = WAITING_CALL_DELAY_SECONDS,
) -> None:
    zadd(ACTIVE_CALLS_KEY, {str(call_key): float(time.time()) + delay_seconds})


def complete_active_call(
    call_key: str,
    *,
    delay_seconds: float = COMPLETED_CALL_DELAY_SECONDS,
) -> None:
    """Park a finished call in the active index with a far-future score.

    Completed calls stay visible to inspection/status tooling instead of being
    removed from the active zset. The future score keeps the forever-loop from
    reprocessing them during normal runtime polling.
    """

    zadd(ACTIVE_CALLS_KEY, {str(call_key): float(time.time()) + delay_seconds})


def remove_active_call(call_key: str) -> None:
    zrem(ACTIVE_CALLS_KEY, str(call_key))


__all__ = [
    "ACTIVE_CALLS_KEY",
    "ACTIVE_WINDOW_LIMIT",
    "COMPLETED_CALL_DELAY_SECONDS",
    "IDLE_SLEEP_SECONDS",
    "WAITING_CALL_DELAY_SECONDS",
    "ActiveCall",
    "active_call_window",
    "bump_active_call",
    "complete_active_call",
    "defer_active_call",
    "oldest_active_call",
    "remove_active_call",
    "seconds_until_next_visible",
    "visible_active_calls",
]
