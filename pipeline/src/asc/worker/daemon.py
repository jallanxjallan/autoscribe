"""Worker daemon entrypoint."""

from dataclasses import dataclass

from asc.models.process.task import WorkerTask
from asc.state.daemon import DEFAULT_CLAIM_TIMEOUT_SECONDS, configure_logging, run_daemon
from asc.worker import inbox as worker_inbox
from asc.worker.execute import WorkerExecutor


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
    wait: bool = False,
) -> WorkerRunReport:
    """Claim and execute one worker task."""

    if wait:
        claimed = worker_inbox.daemon_claim(
            timeout=timeout or 0,
            empty_limit=empty_limit,
        )
    else:
        claimed = worker_inbox.claim()

    if claimed is None:
        return WorkerRunReport(claimed=False)

    task_key = claimed.strip()
    if not task_key:
        raise ValueError("worker claimed an empty task key")

    print(f"worker claimed_task_key={task_key}", flush=True)

    task = WorkerTask.load(task_key)
    result = WorkerExecutor().execute(task, task_key)

    return WorkerRunReport(
        claimed=True,
        task_key=task_key,
        artifact_key=result.artifact_key,
        failure_key=result.failure_key,
        action=task.action,
    )


def run_forever(
    *,
    timeout: int = DEFAULT_CLAIM_TIMEOUT_SECONDS,
    empty_limit: int | None = None,
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
    """Run one non-blocking worker cycle."""

    configure_logging()
    report = run_once(timeout=0, empty_limit=0, wait=False)
    print(
        f"worker claimed={report.claimed} "
        f"task_key={report.task_key} action={report.action} "
        f"artifact_key={report.artifact_key} failure_key={report.failure_key}"
    )


if __name__ == "__main__":
    main()


__all__ = ["WorkerRunReport", "main", "run_forever", "run_once"]
