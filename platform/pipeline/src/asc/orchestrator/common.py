"""Shared job and artifact helpers."""

from __future__ import annotations

import time
from asc.redis.key import RedisKey
from asc.worker.inbox import post as post_to_worker
from .active import schedule_inflight


def load_job(job_key: str) -> tuple[RedisKey, dict[str, str]]:
    key = RedisKey(job_key)
    raw = key.hgetall()
    if not raw:
        raise KeyError(f"job record does not exist: {job_key}")
    return key, raw


def update_job(key: RedisKey, **values: object) -> None:
    key.hset(mapping={name: str(value) for name, value in values.items()})


def dispatch_runtime(job_key: str, *, identity: str, step: int, now: float | None = None, multiplier: float = 1.0) -> tuple[str, float]:
    current = time.time() if now is None else float(now)
    runtime_key = str(RedisKey(kind="runtime", identity=identity, suffix=str(step)))
    if not RedisKey(runtime_key).exists():
        raise KeyError(f"runtime record does not exist: {runtime_key}")
    post_to_worker(runtime_key)
    score = schedule_inflight(job_key, now=current, multiplier=multiplier)
    job = RedisKey(job_key)
    update_job(
        job,
        step=step,
        step_queued_at=current,
        inspect_after=score,
        retry_count=0,
        last_error="",
    )
    return runtime_key, score


def result_failed(result: dict[str, str]) -> bool:
    status = str(result.get("status", result.get("outcome", "success"))).strip().lower()
    if status in {"failure", "failed", "error"}:
        return True
    success = str(result.get("success", "")).strip().lower()
    return success in {"false", "0", "no"}

__all__ = ["dispatch_runtime", "load_job", "result_failed", "update_job"]
