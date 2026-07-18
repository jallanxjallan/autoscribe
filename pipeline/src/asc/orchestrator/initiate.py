"""New-job initiation.

The active zset contains ``job:<identity>:record`` keys. Initiation sends the
matching ``call:<identity>:record`` key to scrivener, then restores the job to
the active zset with its first positive visibility score.
"""

from __future__ import annotations

from dataclasses import dataclass

from asc.orchestrator.active import restore_new_job, schedule_active_job
from asc.redis.key import RedisKey
from asc.scrivener.inbox import post as post_to_scrivener


@dataclass(frozen=True, slots=True)
class InitiationReport:
    job_key: str
    call_key: str
    active_score: float


def call_key_for_job(job_key: str) -> str:
    job = RedisKey(str(job_key).strip())
    if job.kind != "job" or job.suffix != "record":
        raise ValueError(f"expected job record key, got {job.raw_key!r}")
    return str(RedisKey(kind="call", identity=job.identity, suffix="record"))


def initiate_job(job_key: str) -> InitiationReport:
    key = str(job_key).strip()
    if not key:
        raise ValueError("job_key must be non-empty")

    call_key = call_key_for_job(key)
    if not RedisKey(call_key).exists():
        restore_new_job(key)
        raise KeyError(f"call record does not exist for job {key!r}: {call_key!r}")

    try:
        post_to_scrivener(call_key)
        score = schedule_active_job(key)
    except Exception:
        # The score-zero job was already popped. Restore it so a daemon crash
        # or Redis/queue error cannot silently swallow the job.
        restore_new_job(key)
        raise

    return InitiationReport(job_key=key, call_key=call_key, active_score=score)


__all__ = ["InitiationReport", "call_key_for_job", "initiate_job"]
