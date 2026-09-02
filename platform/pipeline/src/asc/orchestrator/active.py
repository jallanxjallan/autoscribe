"""The single active-job sorted set and its score windows."""

from __future__ import annotations

from dataclasses import dataclass
import time

from asc.redis.key import RedisKey

ACTIVE_JOBS_KEY = RedisKey("state:active:index")
IDLE_SLEEP_SECONDS = 5.0
INFLIGHT_OFFSET_SECONDS = 60.0
MAX_PROCESS_RETRIES = 3

# Failure jobs are visible only to evaluate. Successful jobs are parked beyond it.
FAILURE_WINDOW_OFFSET = float(10 * 365 * 24 * 60 * 60)
FAILURE_WINDOW_WIDTH = float(365 * 24 * 60 * 60)
SUCCESS_WINDOW_OFFSET = float(20 * 365 * 24 * 60 * 60)


@dataclass(frozen=True, slots=True)
class ActiveJob:
    key: str
    score: float


def _claim_range(min_score: float, max_score: float) -> ActiveJob | None:
    members = ACTIVE_JOBS_KEY.zrangebyscore(min_score, max_score, start=0, num=1, withscores=True)
    if not members:
        return None
    member, score = members[0]
    key = str(member).strip()
    value = float(score)
    if not key:
        raise ValueError("state:active:index contained an empty member")
    parsed = RedisKey(key)
    if parsed.kind != "job" or parsed.suffix != "record":
        raise ValueError(f"active member must be job:*:record: {key!r}")
    if ACTIVE_JOBS_KEY.zrem(key) != 1:
        return None
    return ActiveJob(key, value)


def claim_initiate() -> ActiveJob | None:
    return _claim_range(0.0, 0.0)


def claim_process(*, now: float | None = None) -> ActiveJob | None:
    current = time.time() if now is None else float(now)
    return _claim_range(1.0, current)


def failure_bounds(*, now: float | None = None) -> tuple[float, float]:
    current = time.time() if now is None else float(now)
    start = current + FAILURE_WINDOW_OFFSET
    return start, start + FAILURE_WINDOW_WIDTH


def claim_evaluate(*, now: float | None = None) -> ActiveJob | None:
    low, high = failure_bounds(now=now)
    return _claim_range(low, high)


def schedule(job_key: str, score: float) -> float:
    value = float(score)
    ACTIVE_JOBS_KEY.zadd({str(job_key): value})
    return value


def schedule_inflight(job_key: str, *, now: float | None = None, multiplier: float = 1.0) -> float:
    current = time.time() if now is None else float(now)
    return schedule(job_key, current + INFLIGHT_OFFSET_SECONDS * float(multiplier))


def park_failure(job_key: str, *, now: float | None = None) -> float:
    current = time.time() if now is None else float(now)
    return schedule(job_key, current + FAILURE_WINDOW_OFFSET)


def park_success(job_key: str, *, now: float | None = None) -> float:
    current = time.time() if now is None else float(now)
    return schedule(job_key, current + SUCCESS_WINDOW_OFFSET)


ACTIVE_CALLS_KEY = ACTIVE_JOBS_KEY

__all__ = [
    "ACTIVE_CALLS_KEY", "ACTIVE_JOBS_KEY", "ActiveJob", "FAILURE_WINDOW_OFFSET",
    "FAILURE_WINDOW_WIDTH", "IDLE_SLEEP_SECONDS", "INFLIGHT_OFFSET_SECONDS",
    "MAX_PROCESS_RETRIES", "SUCCESS_WINDOW_OFFSET", "claim_evaluate",
    "claim_initiate", "claim_process", "failure_bounds", "park_failure",
    "park_success", "schedule", "schedule_inflight",
]
