"""Scrivener daemon entrypoint and runtime helpers.

Run once from the command line:
    python -m asc.scrivener.daemon

Run forever from imported code:
    from asc.scrivener.daemon import run_forever
    run_forever()
"""

from dataclasses import dataclass

from asc.models.process.event import Committed
from asc.models.process.task import ScrivenerTask
from asc.orchestrator import inbox as orchestrator_inbox
from asc.scrivener import inbox as scrivener_inbox
from asc.scrivener.write import write_task
from asc.state.daemon import DEFAULT_CLAIM_TIMEOUT_SECONDS, configure_logging, run_daemon


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

    task = ScrivenerTask.load(task_key)
    cursor_key = task.cursor_key
    if not cursor_key:
        raise ValueError(f"scrivener task has no cursor_key: {task_key}")

    write_task(task)

    committed = Committed(identity=task.identity)
    committed.save()

    orchestrator_inbox.post(str(committed.redis_key))

    

    return ScrivenerRunReport(
        claimed=True,
        cursor_key=cursor_key,
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
