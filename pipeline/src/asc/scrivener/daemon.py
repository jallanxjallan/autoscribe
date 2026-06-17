"""Scrivener daemon entrypoint and runtime helpers.

Run once from the command line:
    python -m asc.scrivener.daemon

Run forever from imported code:
    from asc.scrivener.daemon import run_forever
    run_forever()
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from asc.models.process.task import ScrivenerTask
from asc.scrivener.write import write_task
from asc.state import orchestrator_queue, scrivener_queue
from asc.state.daemon import DEFAULT_CLAIM_TIMEOUT_SECONDS, idle_empty_limit, run_daemon

log = logging.getLogger(__name__)

DEFAULT_EMPTY_LIMIT = idle_empty_limit(timeout=DEFAULT_CLAIM_TIMEOUT_SECONDS)


@dataclass(frozen=True, slots=True)
class ScrivenerRunReport:
    claimed: bool
    cursor_key: str | None = None
    task_key: str | None = None
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

    task_key = str(getattr(claimed, "key", claimed)).strip()
    if not task_key:
        raise ValueError("scrivener claimed an empty task key")

    task = ScrivenerTask.load(task_key)
    cursor_key = str(getattr(task, "cursor_key", "")).strip()
    if not cursor_key:
        raise ValueError(f"scrivener task has no cursor_key: {task_key}")

    write_task(task)

    # Return the completed task key to orchestrator. Orchestrator can load the
    # task, recover cursor_key from it, and route the next task without mutating
    # RuntimeCursor.
    orchestrator_queue.insert(task_key)

    return ScrivenerRunReport(
        claimed=True,
        cursor_key=cursor_key,
        task_key=task_key,
        action=str(getattr(task, "action", "") or ""),
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


def main() -> ScrivenerRunReport:
    logging.basicConfig(level=os.environ.get("AUTOSCRIBE_LOG_LEVEL", "INFO"))
    report = run_once()
    log.info(
        "scrivener claimed=%s task_key=%s action=%s",
        report.claimed,
        report.task_key,
        report.action,
    )
    return report


if __name__ == "__main__":
    main()


__all__ = ["ScrivenerRunReport", "main", "run_forever", "run_once"]
