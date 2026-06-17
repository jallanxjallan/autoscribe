"""Orchestrator entrypoint.

Command-line use runs a single orchestration pass:
    python -m asc.orchestrator.daemon

Long-running daemon use is explicit from an importer:
    from asc.orchestrator.daemon import run_forever
    run_forever()
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from asc.state.daemon import DEFAULT_CLAIM_TIMEOUT_SECONDS, idle_empty_limit, run_daemon
from .wiring import build_service


DEFAULT_EMPTY_LIMIT = idle_empty_limit(timeout=DEFAULT_CLAIM_TIMEOUT_SECONDS)


@dataclass(frozen=True, slots=True)
class OrchestratorRunReport:
    claimed: bool


def configure_logging() -> None:
    logging.basicConfig(level=os.environ.get("AUTOSCRIBE_LOG_LEVEL", "INFO"))


def run_once(
    *,
    timeout: int | None = None,
    empty_limit: int | None = None,
    wait: bool = False,
) -> OrchestratorRunReport:
    claimed = build_service().run_once(timeout=timeout, empty_limit=empty_limit, wait=wait)
    return OrchestratorRunReport(claimed=claimed)


def run_forever(
    *,
    timeout: int = DEFAULT_CLAIM_TIMEOUT_SECONDS,
    empty_limit: int = DEFAULT_EMPTY_LIMIT,
) -> None:
    configure_logging()
    run_daemon(
        name="orchestrator",
        run_once=run_once,
        timeout=timeout,
        empty_limit=empty_limit,
    )


def main() -> None:
    configure_logging()
    report = run_once(timeout=0, empty_limit=0, wait=False)
    print(f"orchestrator claimed={report.claimed}")


if __name__ == "__main__":
    main()


__all__ = ["OrchestratorRunReport", "main", "run_forever", "run_once"]
