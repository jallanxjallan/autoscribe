"""Scrivener daemon entrypoint and runtime helpers.

Run once from the command line:
    python -m asc.scrivener.daemon

Run forever from imported code:
    from asc.scrivener.daemon import run_forever
    run_forever()
"""

from dataclasses import dataclass

from asc.orchestrator import inbox as orchestrator_inbox
from asc.scrivener import inbox as scrivener_inbox
from asc.scrivener.execute import ScrivenerExecutor
from asc.state.daemon import DEFAULT_CLAIM_TIMEOUT_SECONDS, configure_logging, run_daemon


@dataclass(frozen=True, slots=True)
class ScrivenerRunReport:
    claimed: bool
    task_key: str | None = None
    action: str | None = None
    output_key: str | None = None


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

    task_key = str(claimed).strip()
    if not task_key:
        raise ValueError("scrivener claimed an empty task key")

    result = ScrivenerExecutor().execute(task_key)
    orchestrator_inbox.post(result.output_key)

    return ScrivenerRunReport(
        claimed=True,
        task_key=result.task_key,
        action=result.action,
        output_key=result.output_key,
    )


def run_forever(
    *,
    timeout: int = DEFAULT_CLAIM_TIMEOUT_SECONDS,
    empty_limit: int | None = None,
) -> None:
    """Run the scrivener daemon loop until idle shutdown or interruption."""

    configure_logging()
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
        f"task_key={report.task_key} action={report.action} "
        f"output_key={report.output_key}"
    )


if __name__ == "__main__":
    main()


__all__ = ["ScrivenerRunReport", "main", "run_forever", "run_once"]
