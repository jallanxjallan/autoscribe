from __future__ import annotations

import logging
from dataclasses import dataclass

from asc.scrivener.jobs import RuntimeCursor, ScrivenerJob
from asc.scrivener.write import write_job
from asc.state import orchestrator_queue, scrivener_queue

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ScrivenerRunReport:
    claimed: bool
    cursor_key: str | None = None
    job_key: str | None = None
    action: str | None = None


def run_once(*, timeout: int | None = None) -> ScrivenerRunReport:
    # ``timeout=0`` is the manual smoke-test path used by ``python -m``.
    # Redis BLPOP treats zero as "block forever", but for this package we
    # want parity with orchestrator: one non-blocking pass and a no-op report
    # when the queue is empty.
    claimed = (
        scrivener_queue.claim()
        if timeout is None or timeout == 0
        else scrivener_queue.block_claim(timeout=timeout)
    )
    if claimed is None:
        return ScrivenerRunReport(claimed=False)

    cursor_key = claimed.cursor_key
    cursor = RuntimeCursor.load(cursor_key)
    job_key = cursor.current_job_key
    job = ScrivenerJob.load(job_key)

    write_job(job)
    orchestrator_queue.insert(cursor_key)

    return ScrivenerRunReport(
        claimed=True,
        cursor_key=cursor_key,
        job_key=job_key,
        action=job.action,
    )


def run_forever(*, timeout: int | None = 5) -> None:
    while True:
        report = run_once(timeout=timeout)
        if report.claimed:
            log.info(
                "scrivener wrote %s job=%s cursor=%s",
                report.action,
                report.job_key,
                report.cursor_key,
            )


__all__ = ["ScrivenerRunReport", "run_forever", "run_once"]
