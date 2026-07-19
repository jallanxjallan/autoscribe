"""Initiate daemon: consume only score-zero jobs."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import time

from asc.scrivener.inbox import post as post_to_scrivener
from asc.state.daemon import configure_logging
from asc.redis.key import RedisKey
from .active import IDLE_SLEEP_SECONDS, claim_initiate, schedule
from .common import dispatch_runtime, load_job

LOG = logging.getLogger(__name__)

@dataclass(frozen=True, slots=True)
class InitiateReport:
    claimed: bool
    job_key: str | None = None
    call_key: str | None = None
    runtime_key: str | None = None
    active_score: float | None = None


def run_cycle(*, wait: bool = True) -> InitiateReport:
    claimed = claim_initiate()
    if claimed is None:
        if wait:
            time.sleep(IDLE_SLEEP_SECONDS)
        return InitiateReport(False)
    try:
        job, raw = load_job(claimed.key)
        step = int(raw.get("step", raw.get("response_ordinal_hint", "0")) or 0)
        if step != 0:
            raise ValueError(f"initiate window job must have step 0: {claimed.key}")
        call_key = str(RedisKey(kind="call", identity=job.identity, suffix="record"))
        if not RedisKey(call_key).exists():
            raise KeyError(f"call record does not exist: {call_key}")
        post_to_scrivener(call_key)
        runtime_key, score = dispatch_runtime(claimed.key, identity=job.identity, step=1)
    except Exception:
        schedule(claimed.key, claimed.score)
        raise
    LOG.info("initiate job=%s call=%s runtime=%s score=%s", claimed.key, call_key, runtime_key, score)
    return InitiateReport(True, claimed.key, call_key, runtime_key, score)


def run_forever() -> None:
    configure_logging()
    LOG.info("initiate daemon start")
    while True:
        run_cycle(wait=True)


def main() -> None:
    run_forever()

if __name__ == "__main__":
    main()
