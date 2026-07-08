"""Active-call zset helpers for the orchestrator.

The enqueuer owns call creation and inserts ``call:<identity>:record`` into the
active zset with a timestamp score. The orchestrator treats due scores as live
work, retry scores as delayed work, and a far-future terminal score as done.
"""

from __future__ import annotations

from dataclasses import dataclass
import time

from asc.redis.key import RedisKey
from asc.redis.primitives.zsets import zadd, zrange, zrem, zscore


ACTIVE_CALLS_KEY = RedisKey("state:active:index")
ACTIVE_WINDOW_LIMIT = 16
WAITING_CALL_DELAY_SECONDS = 3.0
RETRY_CALL_DELAY_SECONDS = 5 * 60.0
IDLE_SLEEP_SECONDS = 5.0
TERMINAL_CALL_SCORE = 2145916800.0  # 2038-01-01T00:00:00Z
LEGACY_PARKED_CALL_SCORE = 0.0


@dataclass(frozen=True, slots=True)
class ActiveCall:
    key: str
    score: float

    @property
    def visible(self) -> bool:
        return self.score > LEGACY_PARKED_CALL_SCORE and self.score <= time.time()


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

    # Legacy terminal calls may still be parked at score 0. Ignore those. New
    # terminal calls are parked far in the future so current and retryable work
    # naturally stays ahead of them in score order.
    members = zrange(ACTIVE_CALLS_KEY, 0, -1)
    calls: list[ActiveCall] = []

    for member in members:
        key = str(member).strip()
        if not key:
            continue
        score = zscore(ACTIVE_CALLS_KEY, key)
        if score is None:
            continue
        active_call = ActiveCall(key=key, score=float(score))
        if active_call.score <= LEGACY_PARKED_CALL_SCORE:
            continue
        calls.append(active_call)

    return sorted(calls, key=lambda call: call.score)[: max(0, limit)]


def _target_active_calls(*, target_keys: set[str]) -> list[ActiveCall]:
    calls: list[ActiveCall] = []

    for raw in target_keys:
        key = str(raw).strip()
        if not key:
            continue
        score = zscore(ACTIVE_CALLS_KEY, key)
        if score is None:
            continue
        active_call = ActiveCall(key=key, score=float(score))
        if active_call.score <= LEGACY_PARKED_CALL_SCORE:
            continue
        calls.append(active_call)

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
        else [call for call in calls if call.score > LEGACY_PARKED_CALL_SCORE]
    )
    if not window:
        return None

    delay = sorted(window, key=lambda call: call.score)[0].score - time.time()
    if delay <= 0:
        return 0.0
    return min(delay, IDLE_SLEEP_SECONDS)


def activate_active_call(call_key: str) -> None:
    zadd(ACTIVE_CALLS_KEY, {str(call_key): float(time.time())})


def bump_active_call(call_key: str) -> None:
    zadd(ACTIVE_CALLS_KEY, {str(call_key): float(time.time())})


def defer_active_call(
    call_key: str,
    *,
    delay_seconds: float = WAITING_CALL_DELAY_SECONDS,
) -> None:
    zadd(ACTIVE_CALLS_KEY, {str(call_key): float(time.time()) + delay_seconds})


def retry_active_call(
    call_key: str,
    *,
    delay_seconds: float = RETRY_CALL_DELAY_SECONDS,
) -> None:
    zadd(ACTIVE_CALLS_KEY, {str(call_key): float(time.time()) + delay_seconds})


def complete_active_call(call_key: str) -> None:
    zadd(ACTIVE_CALLS_KEY, {str(call_key): TERMINAL_CALL_SCORE})


def remove_active_call(call_key: str) -> None:
    zrem(ACTIVE_CALLS_KEY, str(call_key))


__all__ = [
    "ACTIVE_CALLS_KEY",
    "ACTIVE_WINDOW_LIMIT",
    "IDLE_SLEEP_SECONDS",
    "LEGACY_PARKED_CALL_SCORE",
    "TERMINAL_CALL_SCORE",
    "RETRY_CALL_DELAY_SECONDS",
    "WAITING_CALL_DELAY_SECONDS",
    "ActiveCall",
    "activate_active_call",
    "active_call_window",
    "bump_active_call",
    "complete_active_call",
    "defer_active_call",
    "oldest_active_call",
    "remove_active_call",
    "retry_active_call",
    "seconds_until_next_visible",
    "visible_active_calls",
]
