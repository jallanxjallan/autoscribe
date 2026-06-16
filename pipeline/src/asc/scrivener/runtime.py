from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from asc.scrivener.jobs import LedgerJobRecord
from asc.scrivener.write import write_job
from asc.state import orchestrator_queue, scrivener_queue
from asc.state.daemon import DEFAULT_CLAIM_TIMEOUT_SECONDS, idle_empty_limit, run_daemon

log = logging.getLogger(__name__)

DEFAULT_EMPTY_LIMIT = idle_empty_limit(timeout=DEFAULT_CLAIM_TIMEOUT_SECONDS)


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
        claimed = scrivener_queue.claim()
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
        action=str(getattr(job, "action", "") or getattr(job, "handler", "") or ""),
    )


def run_forever(
    *,
    timeout: int | None = DEFAULT_CLAIM_TIMEOUT_SECONDS,
    empty_limit: int | None = DEFAULT_EMPTY_LIMIT,
) -> None:
    run_daemon(
        name="scrivener",
        run_once=run_once,
        timeout=timeout,
        empty_limit=empty_limit,
    )


def main() -> None:
    logging.basicConfig(level=os.environ.get("AUTOSCRIBE_LOG_LEVEL", "INFO"))
    run_forever()


__all__ = ["ScrivenerRunReport", "main", "run_forever", "run_once"]
