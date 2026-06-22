"""Orchestrator daemon entrypoint and runtime helpers.

Run once from the command line:
    python -m asc.orchestrator.daemon

Run forever from imported code:
    from asc.orchestrator.daemon import run_forever
    run_forever()
"""

from dataclasses import dataclass

from asc.state.daemon import DEFAULT_CLAIM_TIMEOUT_SECONDS, configure_logging, run_daemon

from . import inbox
from .handler import handle_message


@dataclass(frozen=True, slots=True)
class OrchestratorRunReport:
    claimed: bool


def run_once(
    *,
    timeout: int | None = None,
    empty_limit: int | None = None,
    wait: bool = False,
) -> OrchestratorRunReport:
    """Claim and route one orchestrator inbox item."""

    if wait:
        claimed = inbox.daemon_claim(timeout=timeout, empty_limit=empty_limit)
    else:
        claimed = inbox.claim()

    if claimed is None:
        return OrchestratorRunReport(claimed=False)

    handle_message(claimed)
    WorkerTask -> Task(package="worker", action="...")
ScrivenerTask -> Task(package="scrivener", action="...")
Committed -> Outcome(result="success")
failure marker -> Outcome(result="failure", error_code=..., error_message=...)
    return OrchestratorRunReport(claimed=True)


def run_forever(
    *,
    timeout: int = DEFAULT_CLAIM_TIMEOUT_SECONDS,
    empty_limit: int | None = None,
) -> None:
    """Run the orchestrator daemon loop until idle shutdown or interruption."""

    configure_logging()
    run_daemon(
        name="orchestrator",
        run_once=lambda *, timeout=None, empty_limit=None, wait=True: run_once(
            timeout=timeout,
            empty_limit=empty_limit,
            wait=True,
        ),
        timeout=timeout,
        empty_limit=empty_limit,
    )


def main() -> None:
    """Run one orchestrator cycle from the command line."""

    configure_logging()
    report = run_once()
    print(f"orchestrator claimed={report.claimed}")


if __name__ == "__main__":
    main()


__all__ = ["OrchestratorRunReport", "main", "run_forever", "run_once"]
