"""New-job initiation daemon.

This daemon consumes only score-zero ``job:*:record`` entries from
``state:active:index``. It posts the matching call-record key to scrivener and
gives the job its first positive visibility score. No orchestrator task or
handler layer is involved.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import time

from asc.orchestrator.active import IDLE_SLEEP_SECONDS, claim_new_job
from asc.orchestrator.initiate import initiate_job
from asc.state.daemon import configure_logging


LOG = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class OrchestratorRunReport:
    claimed: bool
    job_key: str | None = None
    call_key: str | None = None
    active_score: float | None = None
    action: str = "sleep"


def run_cycle(*, wait: bool = True) -> OrchestratorRunReport:
    claimed = claim_new_job()
    if claimed is None:
        if wait:
            time.sleep(IDLE_SLEEP_SECONDS)
        return OrchestratorRunReport(claimed=False)

    result = initiate_job(claimed.key)
    LOG.info(
        "orchestrator operation=initiate job_key=%s call_key=%s active_score=%s",
        result.job_key,
        result.call_key,
        result.active_score,
    )
    return OrchestratorRunReport(
        claimed=True,
        job_key=result.job_key,
        call_key=result.call_key,
        active_score=result.active_score,
        action="initiate",
    )


def run_forever() -> None:
    configure_logging()
    LOG.info("orchestrator initiation daemon start")
    while True:
        run_cycle(wait=True)


def main() -> None:
    run_forever()


if __name__ == "__main__":
    main()


__all__ = ["OrchestratorRunReport", "main", "run_cycle", "run_forever"]
