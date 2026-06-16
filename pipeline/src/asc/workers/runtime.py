from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from asc.state import worker_queue
from asc.state.daemon import DEFAULT_CLAIM_TIMEOUT_SECONDS, idle_empty_limit, run_daemon
from asc.workers.execute import WorkerExecutor

log = logging.getLogger(__name__)

DEFAULT_EMPTY_LIMIT = idle_empty_limit(timeout=DEFAULT_CLAIM_TIMEOUT_SECONDS)


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
        claimed = worker_queue.claim()
    if claimed is None:
        return WorkerRunReport(claimed=False)

    job_key = str(getattr(claimed, "key", claimed)).strip()
    if not job_key:
        raise ValueError("worker claimed an empty job key")

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
    run_daemon(
        name="worker",
        run_once=run_once,
        timeout=timeout,
        empty_limit=empty_limit,
    )


def main() -> None:
    """Run the worker daemon.

    Direct module execution is the daemon path:
        python -m asc.workers.daemon
    """

    logging.basicConfig(level=os.environ.get("AUTOSCRIBE_LOG_LEVEL", "INFO"))
    run_forever()


__all__ = ["WorkerRunReport", "main", "run_forever", "run_once"]
