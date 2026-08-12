"""Create and register orchestration jobs."""

from __future__ import annotations

from asc.models.process.job import Job
from asc.redis.key import RedisKey
from asc.redis.primitives.zsets import zadd, zrem

# The user will rename this key separately.
ACTIVE_JOBS_KEY = RedisKey("state:active:index")
INITIAL_JOB_SCORE = 0.0


def create_job(*, call_identity: str, plan_identity: str, total_steps: int) -> Job:
    """Build the deterministic job record for one materialized call."""

    return Job(
        identity=call_identity,
        plan_identity=plan_identity,
        total_steps=total_steps,
    )


def activate_job(job: Job) -> None:
    """Persist a job and expose its key to the orchestrator."""

    job.save()
    try:
        zadd(ACTIVE_JOBS_KEY, {job.raw_key: INITIAL_JOB_SCORE})
    except Exception:
        job.delete()
        raise


def deactivate_job(job: Job) -> None:
    """Remove a partially activated job during enqueue rollback."""

    zrem(ACTIVE_JOBS_KEY, job.raw_key)
    job.delete()


__all__ = [
    "ACTIVE_JOBS_KEY",
    "INITIAL_JOB_SCORE",
    "activate_job",
    "create_job",
    "deactivate_job",
]
