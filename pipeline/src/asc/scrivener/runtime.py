from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from asc.scrivener.jobs import LedgerJobRecord
from asc.scrivener.write import write_job
from asc.state import orchestrator_queue, scrivener_queue

log = logging.getLogger(__name__)

DEFAULT_CLAIM_TIMEOUT_SECONDS = int(os.environ.get("AUTOSCRIBE_DAEMON_CLAIM_TIMEOUT", "5"))
DEFAULT_EMPTY_LIMIT = int(os.environ.get("AUTOSCRIBE_DAEMON_EMPTY_LIMIT", "60"))


@dataclass(frozen=True, slots=True)
class ScrivenerRunReport:
    claimed: bool
    cursor_key: str | None = None
    job_key: str | None = None
    action: str | None = None


def run_once(
    *,
    timeout: int | None = None,
    empty_limit: int | None = None,
    wait: bool = False,
) -> ScrivenerRunReport:
    if wait:
        claimed = scrivener_queue.daemon_claim(timeout=timeout, empty_limit=empty_limit)
    else:
        claimed = scrivener_queue.daemon_drain_claim()
    if claimed is None:
        return ScrivenerRunReport(claimed=False)

    job_key = str(getattr(claimed, "key", claimed)).strip()
    if not job_key:
        raise ValueError("scrivener claimed an empty job key")

    job = LedgerJobRecord.load(job_key)
    cursor_key = str(getattr(job, "cursor_key", "")).strip()
    if not cursor_key:
        raise ValueError(f"scrivener job has no cursor_key: {job_key}")

    write_job(job)

    # Return the completed job key to the orchestrator. The orchestrator can load
    # the job, recover the cursor_key from it, and route the next job without
    # mutating RuntimeCursor.
    orchestrator_queue.insert(job_key)

    return ScrivenerRunReport(
        claimed=True,
        cursor_key=cursor_key,
        job_key=job_key,
        action=job.action,
    )


def _empty_message(timeout: int | None, empty_limit: int | None) -> str:
    actual_timeout = int(timeout or DEFAULT_CLAIM_TIMEOUT_SECONDS)
    actual_limit = int(empty_limit or DEFAULT_EMPTY_LIMIT)
    waited = actual_timeout * actual_limit
    return f"scrivener queue empty after {actual_limit} cycles ({waited} seconds); daemon exiting, restart required"


def run_forever(
    *,
    timeout: int | None = DEFAULT_CLAIM_TIMEOUT_SECONDS,
    empty_limit: int | None = DEFAULT_EMPTY_LIMIT,
) -> None:
    report = run_once(timeout=timeout, empty_limit=empty_limit, wait=True)
    if not report.claimed:
        message = _empty_message(timeout, empty_limit)
        log.warning(message)
        print(message, flush=True)
        return

    while report.claimed:
        log.info("scrivener wrote %s job=%s cursor=%s", report.action, report.job_key, report.cursor_key)
        report = run_once(timeout=timeout, empty_limit=empty_limit, wait=False)
        if not report.claimed:
            message = _empty_message(timeout, empty_limit)
            log.warning(message)
            print(message, flush=True)
            return


def main() -> None:
    logging.basicConfig(level=os.environ.get("AUTOSCRIBE_LOG_LEVEL", "INFO"))
    run_forever()


__all__ = ["ScrivenerRunReport", "main", "run_forever", "run_once"]
