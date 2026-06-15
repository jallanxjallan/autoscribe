from __future__ import annotations

import logging
from dataclasses import dataclass

from asc.scrivener.jobs import cursor_key_from_claim, job_key_from_cursor, load_cursor, load_job
from asc.scrivener.queues import claim_scrivener_cursor, post_cursor_to_orchestrator
from asc.scrivener.writers.calls import insert_call_from_job

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ScrivenerRunReport:
    claimed: bool
    cursor_key: str | None = None
    job_key: str | None = None


def run_once(*, timeout: int | None = None) -> ScrivenerRunReport:
    """Claim one cursor, write its current job as a call row, repost cursor.

    Scrivener does not decide workflow state.  Its custody is deliberately tiny:

    1. claim a cursor from the Scrivener queue
    2. load the cursor
    3. load ``cursor.current_job``
    4. insert the call row in the ledger
    5. post the same cursor to the orchestrator queue
    """

    claimed = claim_scrivener_cursor(timeout=timeout)
    cursor_key = cursor_key_from_claim(claimed)

    if cursor_key is None:
        return ScrivenerRunReport(claimed=False)

    cursor = load_cursor(cursor_key)
    job_key = job_key_from_cursor(cursor)
    job = load_job(job_key)

    insert_call_from_job(job)
    post_cursor_to_orchestrator(cursor_key)

    return ScrivenerRunReport(claimed=True, cursor_key=cursor_key, job_key=job_key)


def run_forever(*, timeout: int | None = 5) -> None:
    while True:
        report = run_once(timeout=timeout)
        if report.claimed:
            log.info(
                "scrivener wrote call job=%s cursor=%s",
                report.job_key,
                report.cursor_key,
            )


__all__ = ["ScrivenerRunReport", "run_forever", "run_once"]
