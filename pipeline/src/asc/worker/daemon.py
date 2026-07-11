"""Worker daemon entrypoint."""

from dataclasses import dataclass
import logging

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


def process_next(*, timeout: int = 0) -> WorkerRunReport:
    """Claim and execute the next worker task."""

    claimed = worker_inbox.daemon_claim(timeout=timeout, empty_limit=None)
    if claimed is None:
        return WorkerRunReport(claimed=False)

    task_key = claimed.strip()
    if not task_key:
        raise ValueError("worker claimed an empty task key")

    LOG.info("worker operation=claimed task_key=%s", task_key)
    result = WorkerExecutor().execute(task_key)

    report = WorkerRunReport(
        claimed=True,
        task_key=result.task_key,
        artifact_key=result.artifact_key,
        failure_key=result.failure_key,
        action=result.action,
    )
    LOG.info(
        "worker operation=executed task_key=%s action=%s artifact_key=%s failure_key=%s",
        report.task_key,
        report.action,
        report.artifact_key,
        report.failure_key,
    )
    return report


def run_forever(*, timeout: int = DEFAULT_CLAIM_TIMEOUT_SECONDS) -> None:
    """Run the worker daemon until process termination."""

    configure_logging()
    run_daemon(name="worker", run_cycle=process_next, timeout=timeout)


def main() -> None:
    run_forever()


if __name__ == "__main__":
    main()


__all__ = ["WorkerRunReport", "main", "process_next", "run_forever"]
