"""Worker daemon entrypoint.

Command-line behavior:
    python -m asc.worker.daemon

runs one worker claim cycle and exits.

Imported behavior:
    from asc.worker.daemon import run_forever

runs the long-lived daemon loop.
"""

from dataclasses import dataclass

from asc.models.process.task import Outcome, Task
from asc.orchestrator import inbox as orchestrator_inbox
from asc.state.daemon import DEFAULT_CLAIM_TIMEOUT_SECONDS, configure_logging, run_daemon
from asc.worker import inbox as worker_inbox
from asc.worker.execute import WorkerExecutor


@dataclass(slots=True)
class WorkerRunReport:
    claimed: bool
    cursor_key: str | None = None
    task_key: str | None = None
    output_key: str | None = None
    outcome_key: str | None = None
    action: str | None = None


def run_once(
    *,
    timeout: int | None = None,
    empty_limit: int | None = None,
    wait: bool = False,
) -> WorkerRunReport:
    """Claim and execute one worker task."""

    if wait:
        claimed = worker_inbox.block_claim(
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

    task = Task.load(task_key)
    output_key: str | None = None

    try:
        result = WorkerExecutor().execute(task_key)
        output_key = result.output_key

        outcome = Outcome.model_validate({
            **task.model_dump(mode="json"),
            "identity": task.identity,
            "task_identity": task.identity,
            "result": "success",
            "output_key": output_key,
        })

    except Exception as e:
        outcome = Outcome.model_validate({
            **task.model_dump(mode="json"),
            "identity": task.identity,
            "task_identity": task.identity,
            "result": "failure",
            "error": str(e),
        })

    outcome_key = outcome.save()
    orchestrator_inbox.post(outcome_key)

    return WorkerRunReport(
        claimed=True,
        cursor_key=task.cursor_key,
        task_key=task_key,
        output_key=output_key,
        outcome_key=outcome_key,
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
        run_once=lambda **kwargs: run_once(wait=True, **kwargs),
        timeout=timeout,
        empty_limit=empty_limit,
    )


def main() -> None:
    """Run one worker cycle from the command line."""

    configure_logging()
    report = run_once(timeout=0, empty_limit=0, wait=False)
    print(
        f"worker claimed={report.claimed} "
        f"task_key={report.task_key} action={report.action} "
        f"output_key={report.output_key} outcome_key={report.outcome_key}"
    )


if __name__ == "__main__":
    main()


__all__ = ["WorkerRunReport", "main", "run_forever", "run_once"]