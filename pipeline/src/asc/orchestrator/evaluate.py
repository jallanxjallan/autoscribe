"""Failure evaluator daemon stub for the far-future score window."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import time

from asc.state.daemon import configure_logging
from .active import FAILURE_WINDOW_OFFSET, IDLE_SLEEP_SECONDS, claim_evaluate, schedule
from .common import load_job, update_job

LOG = logging.getLogger(__name__)

@dataclass(frozen=True, slots=True)
class EvaluateReport:
    claimed: bool
    job_key: str | None = None
    action: str = "sleep"
    active_score: float | None = None


def run_cycle(*, wait: bool = True) -> EvaluateReport:
    claimed = claim_evaluate()
    if claimed is None:
        if wait:
            time.sleep(IDLE_SLEEP_SECONDS)
        return EvaluateReport(False)
    try:
        job, raw = load_job(claimed.key)
        attempts = int(raw.get("evaluation_count", "0") or 0) + 1
        # Stub: preserve the failed job in the evaluator's window. A later policy
        # will either retry it with a multiplied inflight offset or park it fatal.
        score = time.time() + FAILURE_WINDOW_OFFSET
        update_job(job, evaluation_count=attempts, last_evaluated_at=time.time())
        schedule(claimed.key, score)
    except Exception:
        schedule(claimed.key, claimed.score)
        raise
    LOG.info("evaluate action=stub-park job=%s score=%s", claimed.key, score)
    return EvaluateReport(True, claimed.key, "stub-park", score)


def run_forever() -> None:
    configure_logging()
    LOG.info("evaluate daemon start")
    while True:
        run_cycle(wait=True)


def main() -> None:
    run_forever()

if __name__ == "__main__":
    main()
