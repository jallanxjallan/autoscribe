"""Orchestrator daemon entrypoint and runtime helpers.

Run once from the command line:
    python -m asc.orchestrator.daemon

Run forever from imported code:
    from asc.orchestrator.daemon import run_forever
    run_forever()
"""

from __future__ import annotations

from dataclasses import dataclass

from asc.state.daemon import DEFAULT_CLAIM_TIMEOUT_SECONDS, configure_logging, run_daemon

from .wiring import build_service


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

    claimed = build_service().run_once(
        timeout=timeout,
        empty_limit=empty_limit,
        wait=wait,
    )
    return OrchestratorRunReport(claimed=bool(claimed))


def run_forever(
    *,
    timeout: int = DEFAULT_CLAIM_TIMEOUT_SECONDS,
    empty_limit: int | None = None,
) -> None:
    """Run the orchestrator daemon loop until idle shutdown or interruption."""

    configure_logging()
    run_daemon(
        name="orchestrator",
        run_once=run_once,
        timeout=timeout,
        empty_limit=empty_limit,
    )


def main() -> None:
    """Run one orchestrator cycle from the command line."""

    configure_logging()
    report = run_once(timeout=0, empty_limit=0, wait=False)
    print(f"orchestrator claimed={report.claimed}")


if __name__ == "__main__":
    main()


__all__ = ["OrchestratorRunReport", "main", "run_forever", "run_once"]
