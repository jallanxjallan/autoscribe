"""Process daemon: inspect due inflight jobs in score range 1..now()."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import time

from asc.redis.key import RedisKey
from asc.models.process.result import record_failure
from asc.scrivener.inbox import post as post_to_scrivener
from asc.state.daemon import configure_logging
from .active import IDLE_SLEEP_SECONDS, MAX_PROCESS_RETRIES, claim_process, park_failure, park_success, schedule, schedule_inflight
from .common import dispatch_runtime, load_job, response_failed, update_job

LOG = logging.getLogger(__name__)

@dataclass(frozen=True, slots=True)
class ProcessReport:
    claimed: bool
    job_key: str | None = None
    action: str = "sleep"
    step: int | None = None
    artifact_key: str | None = None
    active_score: float | None = None


def run_cycle(*, wait: bool = True) -> ProcessReport:
    claimed = claim_process()
    if claimed is None:
        if wait:
            time.sleep(IDLE_SLEEP_SECONDS)
        return ProcessReport(False)
    try:
        report = _process(claimed.key)
    except Exception as exc:
        failure_key = record_failure(
            stage="orchestrator.process",
            exc=exc,
            process_identity=RedisKey(claimed.key).identity,
            job_key=claimed.key,
            claimed_score=claimed.score,
        )
        LOG.error("orchestrator.process job=%s failure_key=%s", claimed.key, failure_key)
        schedule(claimed.key, claimed.score)
        raise
    LOG.info("process action=%s job=%s step=%s artifact=%s score=%s", report.action, report.job_key, report.step, report.artifact_key, report.active_score)
    return report


def _process(job_key: str) -> ProcessReport:
    now = time.time()
    job, raw = load_job(job_key)
    step = int(raw.get("step", raw.get("response_ordinal_hint", "0")) or 0)
    total_steps = int(raw["total_steps"])
    if step < 1:
        raise ValueError(f"process window job must have step >= 1: {job_key}")

    response_key = str(RedisKey(kind="response", identity=job.identity, suffix=str(step)))
    failure_key = str(RedisKey(kind="failure", identity=job.identity, suffix=str(step)))
    failure = RedisKey(failure_key).hgetall()
    if failure:
        message = (
            failure.get("failure_reason")
            or failure.get("content")
            or "worker reported failure"
        )
        update_job(
            job,
            last_response_key=failure_key,
            last_error=message,
            last_checked_at=now,
        )
        score = park_failure(job_key, now=now)
        return ProcessReport(True, job_key, "failure-window", step, failure_key, score)

    response = RedisKey(response_key).hgetall()
    if not response:
        retries = int(raw.get("retry_count", "0") or 0) + 1
        update_job(job, retry_count=retries, last_checked_at=now, last_error=f"missing {response_key}")
        if retries >= MAX_PROCESS_RETRIES:
            score = park_failure(job_key, now=now)
            return ProcessReport(True, job_key, "failure-window", step, response_key, score)
        score = schedule_inflight(job_key, now=now)
        update_job(job, inspect_after=score)
        return ProcessReport(True, job_key, "recheck", step, response_key, score)

    if response_failed(response):
        message = response.get("failure_reason") or response.get("fail_message") or response.get("error") or "response reported failure"
        update_job(job, last_response_key=response_key, last_error=message, last_checked_at=now)
        score = park_failure(job_key, now=now)
        return ProcessReport(True, job_key, "failure-window", step, response_key, score)

    if step >= total_steps:
        post_to_scrivener(response_key)
        update_job(job, last_response_key=response_key, completed_at=now, last_checked_at=now, retry_count=0)
        score = park_success(job_key, now=now)
        return ProcessReport(True, job_key, "success", step, response_key, score)

    update_job(job, last_response_key=response_key, last_checked_at=now, retry_count=0)
    runtime_key, score = dispatch_runtime(job_key, identity=job.identity, step=step + 1, now=now)
    return ProcessReport(True, job_key, "dispatch", step + 1, runtime_key, score)


def run_forever() -> None:
    configure_logging()
    LOG.info("process daemon start")
    while True:
        run_cycle(wait=True)


def main() -> None:
    run_forever()

if __name__ == "__main__":
    main()
