from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from asc.state import worker_queue
from asc.workers.execute import WorkerExecutor

log = logging.getLogger(__name__)

DEFAULT_CLAIM_TIMEOUT_SECONDS = int(os.environ.get("AUTOSCRIBE_DAEMON_CLAIM_TIMEOUT", "5"))
DEFAULT_EMPTY_LIMIT = int(os.environ.get("AUTOSCRIBE_DAEMON_EMPTY_LIMIT", "60"))


@dataclass(frozen=True, slots=True)
class WorkerRunReport:
    claimed: bool
    cursor_key: str | None = None
    job_key: str | None = None
    output_key: str | None = None


def run_once(
    *,
    timeout: int | None = None,
    empty_limit: int | None = None,
    wait: bool = False,
) -> WorkerRunReport:
    if wait:
        claimed = worker_queue.daemon_claim(timeout=timeout, empty_limit=empty_limit)
    else:
        claimed = worker_queue.daemon_drain_claim()
    if claimed is None:
        return WorkerRunReport(claimed=False)

    job_key = str(getattr(claimed, "key", claimed)).strip()
    result = WorkerExecutor().execute(job_key)
    return WorkerRunReport(
        claimed=True,
        cursor_key=result.cursor_key,
        job_key=result.job_key,
        output_key=result.output_key,
    )

def run_forever(
    *,
    timeout: int | None = DEFAULT_CLAIM_TIMEOUT_SECONDS,
    empty_limit: int | None = DEFAULT_EMPTY_LIMIT,
) -> None:
    report = run_once(timeout=timeout, empty_limit=empty_limit, wait=True)
    if not report.claimed:
        waited = int(timeout or DEFAULT_CLAIM_TIMEOUT_SECONDS) * int(empty_limit or DEFAULT_EMPTY_LIMIT)
        message = (
            f"worker queue empty after {empty_limit} cycles "
            f"({waited} seconds); daemon exiting, restart required"
        )
        log.warning(message)
        print(message, flush=True)
        return

    while report.claimed:
        log.info("worker wrote output=%s job=%s cursor=%s", report.output_key, report.job_key, report.cursor_key)
        report = run_once(timeout=timeout, empty_limit=empty_limit, wait=False)
        if not report.claimed:
            waited = int(timeout or DEFAULT_CLAIM_TIMEOUT_SECONDS) * int(empty_limit or DEFAULT_EMPTY_LIMIT)
            message = (
                f"worker queue empty after {empty_limit} cycles "
                f"({waited} seconds); daemon exiting, restart required"
            )
            log.warning(message)
            print(message, flush=True)
            return

def main() -> None:
    """Run the worker daemon.

    Direct module execution is the daemon path:
        python -m asc.workers.daemon
    """

    logging.basicConfig(level=os.environ.get("AUTOSCRIBE_LOG_LEVEL", "INFO"))
    run_forever()


__all__ = ["WorkerRunReport", "main", "run_forever", "run_once"]
