"""Scrivener daemon entrypoint and runtime helpers.

Run once from the command line:
    python -m asc.scrivener.daemon

Run forever from imported code:
    from asc.scrivener.daemon import run_forever
    run_forever()
"""

from dataclasses import dataclass

from asc.models.process.task import Task, Outcome
from asc.orchestrator import inbox as orchestrator_inbox
from asc.scrivener import inbox as scrivener_inbox
from asc.scrivener.write import write_task
from asc.state.daemon import DEFAULT_CLAIM_TIMEOUT_SECONDS, configure_logging, run_daemon


@dataclass(frozen=True, slots=True)
class ScrivenerRunReport:
    claimed: bool
    # cursor_key: str | None = None
    task_key: str | None = None
    action: str | None = None


def run_once(
    *,
    timeout: int | None = None,
    empty_limit: int | None = None,
    wait: bool = False,
) -> ScrivenerRunReport:
    """Claim and execute one scrivener task."""

    if wait:
        claimed = scrivener_inbox.daemon_claim(
            timeout=timeout or 0,
            empty_limit=empty_limit,
        )
    else:
        claimed = scrivener_inbox.claim()
    if claimed is None:
        return ScrivenerRunReport(claimed=False)

    task_key = claimed
    if not task_key:
        raise ValueError("scrivener claimed an empty task key")

    task = Task.load(task_key)

    try:
        # Smoke-test mode:
        # The new task shape gives scrivener only package/action/cursor_key.
        # The old writers still expect task.source_key, so do not call them
        # until the writers are converted to derive records from the cursor.
        pass

        outcome = Outcome.model_validate({
            **task.model_dump(mode="json"),
            "identity": task.identity,
            "task_identity": task.identity,
            "result": "success",
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
    
    
    return ScrivenerRunReport(
        claimed=True,
        # cursor_key=task.cursor_key,
        task_key=task_key,
        action=task.action,
    )


def run_forever(
    *,
    timeout: int = DEFAULT_CLAIM_TIMEOUT_SECONDS,
    empty_limit: int | None = None,
) -> None:
    """Run the scrivener daemon loop until idle shutdown or interruption."""

    run_daemon(
        name="scrivener",
        run_once=lambda **kwargs: run_once(wait=True, **kwargs),
        timeout=timeout,
        empty_limit=empty_limit,
    )


def main() -> None:
    """Run one scrivener cycle from the command line."""

    configure_logging()
    report = run_once()
    print(
        f"scrivener claimed={report.claimed} "
        f"task_key={report.task_key} action={report.action}"
    )


if __name__ == "__main__":
    main()


__all__ = ["ScrivenerRunReport", "main", "run_forever", "run_once"]
