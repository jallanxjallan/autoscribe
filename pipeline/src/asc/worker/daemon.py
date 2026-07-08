"""Worker daemon entrypoint.

``python -m asc.worker.daemon`` runs the production worker loop until stopped by
``asc run stop``.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging

from asc.models.process.task import WorkerTask
from asc.state.daemon import DEFAULT_CLAIM_TIMEOUT_SECONDS, configure_logging, run_daemon
from asc.worker import inbox as worker_inbox
from asc.worker.execute import WorkerExecutor


LOG = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class WorkerRunReport:
    claimed: bool
    task_key: str | None = None
    artifact_key: str | None = None
    failure_key: str | None = None
    action: str | None = None


def run_once(
    *,
    timeout: int | None = None,
    empty_limit: int | None = None,
    wait: bool = True,
) -> WorkerRunReport:
    """Claim and execute one worker task."""

    claimed = worker_inbox.daemon_claim(timeout=timeout or 0, empty_limit=None) if wait else worker_inbox.claim()

    if claimed is None:
        return WorkerRunReport(claimed=False)

    task_key = str(claimed).strip()
    if not task_key:
        raise ValueError("worker claimed an empty task key")

    LOG.info("worker operation=claimed task_key=%s", task_key)

    task = WorkerTask.load(task_key)
    result = WorkerExecutor().execute(task, task_key)

    report = WorkerRunReport(
        claimed=True,
        task_key=task_key,
        artifact_key=result.artifact_key,
        failure_key=result.failure_key,
        action=task.action,
    )
    LOG.info(
        "worker operation=executed task_key=%s action=%s artifact_key=%s failure_key=%s",
        report.task_key,
        report.action,
        report.artifact_key,
        report.failure_key,
    )
    return report


def run_forever(*, timeout: int = DEFAULT_CLAIM_TIMEOUT_SECONDS, empty_limit: int | None = None) -> None:
    """Run the worker daemon loop until process termination."""

    configure_logging()
    run_daemon(name="worker", run_once=run_once, timeout=timeout, empty_limit=empty_limit)


def main() -> None:
    """Run the production worker loop."""

    run_forever()


if __name__ == "__main__":
    main()


__all__ = ["WorkerRunReport", "main", "run_forever", "run_once"]
