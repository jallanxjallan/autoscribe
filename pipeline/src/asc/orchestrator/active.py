"""Active-job zset helpers.

Score ``0`` means a newly enqueued job awaiting initiation. Positive scores
are reserved for subsequent orchestration visibility scheduling.
"""

from __future__ import annotations

from dataclasses import dataclass
import time

from asc.redis.key import RedisKey


ACTIVE_JOBS_KEY = RedisKey("state:active:index")
NEW_JOB_SCORE = 0.0
IDLE_SLEEP_SECONDS = 5.0


@dataclass(frozen=True, slots=True)
class ActiveJob:
    key: str
    score: float


def claim_new_job() -> ActiveJob | None:
    """Atomically pop the lowest member when it is a score-zero job.

    ``ZPOPMIN`` is the ownership boundary. If the lowest member is not a new
    job, it is immediately restored unchanged and no work is claimed.
    """

    items = ACTIVE_JOBS_KEY.zpopmin(1)
    if not items:
        return None

    member, score = items[0]
    job = ActiveJob(key=str(member).strip(), score=float(score))
    if not job.key:
        raise ValueError("active-job zset contained an empty member")

    if job.score != NEW_JOB_SCORE:
        ACTIVE_JOBS_KEY.zadd({job.key: job.score})
        return None

    key = RedisKey(job.key)
    if key.kind != "job" or key.suffix != "record":
        ACTIVE_JOBS_KEY.zadd({job.key: job.score})
        raise ValueError(f"new active entry must be a job record key: {job.key!r}")

    return job


def restore_new_job(job_key: str) -> None:
    ACTIVE_JOBS_KEY.zadd({str(job_key): NEW_JOB_SCORE})


def schedule_active_job(job_key: str, *, score: float | None = None) -> float:
    next_score = float(time.time()) if score is None else float(score)
    if next_score <= NEW_JOB_SCORE:
        raise ValueError("active-job visibility score must be greater than zero")
    ACTIVE_JOBS_KEY.zadd({str(job_key): next_score})
    return next_score


__all__ = [
    "ACTIVE_JOBS_KEY",
    "IDLE_SLEEP_SECONDS",
    "NEW_JOB_SCORE",
    "ActiveJob",
    "claim_new_job",
    "restore_new_job",
    "schedule_active_job",
]
