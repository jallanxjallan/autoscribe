"""Worker daemon entrypoint.

Command-line behavior:

    python -m asc.workers.daemon

runs one worker claim cycle and exits.

Imported behavior:

    from asc.workers.daemon import run_forever

runs the long-lived daemon loop.
"""

from __future__ import annotations

from dataclasses import dataclass

from asc.state.daemon import DEFAULT_CLAIM_TIMEOUT_SECONDS, configure_logging, idle_empty_limit, run_daemon
from asc.workers import inbox as worker_inbox
from asc.workers.execute import WorkerExecutor

DEFAULT_EMPTY_LIMIT = idle_empty_limit(timeout=DEFAULT_CLAIM_TIMEOUT_SECONDS)


@dataclass(frozen=True, slots=True)
class WorkerRunReport:
    claimed: bool
    cursor_key: str | None = None
    task_key: str | None = None
    output_key: str | None = None


def run_once(
    *,
    timeout: int | None = None,
    empty_limit: int | None = None,
    wait: bool = False,
) -> WorkerRunReport:
    """Claim and execute one worker task."""

    if wait:
        claimed = worker_inbox.block_claim(timeout=timeout or 0, empty_limit=empty_limit)
    else:
        claimed = worker_inbox.claim()
    if claimed is None:
        return WorkerRunReport(claimed=False)

    task_key = str(claimed).strip()
    if not task_key:
        raise ValueError("worker claimed an empty task key")

    result = WorkerExecutor().execute(task_key)
    return WorkerRunReport(
        claimed=True,
        cursor_key=result.cursor_key,
        task_key=result.task_key,
        output_key=result.output_key,
    )


def run_forever(
    *,
    timeout: int = DEFAULT_CLAIM_TIMEOUT_SECONDS,
    empty_limit: int | None = DEFAULT_EMPTY_LIMIT,
) -> None:
    """Run the worker daemon loop until idle shutdown or interruption."""

    configure_logging()
    run_daemon(
        name="worker",
        run_once=run_once,
        timeout=timeout,
        empty_limit=empty_limit,
    )


def main() -> None:
    """Run one worker cycle from the command line."""

    configure_logging()
    report = run_once(timeout=0, empty_limit=0, wait=False)
    print(f"worker claimed={report.claimed}")


if __name__ == "__main__":
    main()


__all__ = ["WorkerRunReport", "main", "run_forever", "run_once"]
