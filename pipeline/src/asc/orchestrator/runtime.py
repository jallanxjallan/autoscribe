"""Command runtime for the orchestrator daemon."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from asc.state.daemon import DEFAULT_CLAIM_TIMEOUT_SECONDS, idle_empty_limit, run_daemon

from .wiring import build_service

log = logging.getLogger(__name__)

DEFAULT_EMPTY_LIMIT = idle_empty_limit(timeout=DEFAULT_CLAIM_TIMEOUT_SECONDS)


@dataclass(frozen=True, slots=True)
class OrchestratorRunReport:
    claimed: bool


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
    timeout: int | None = DEFAULT_CLAIM_TIMEOUT_SECONDS,
    empty_limit: int | None = DEFAULT_EMPTY_LIMIT,
) -> None:
    run_daemon(
        name="orchestrator",
        run_once=run_once,
        timeout=timeout,
        empty_limit=empty_limit,
    )


def main() -> None:
    """Run the orchestrator daemon.

    Direct module execution is the long-running daemon path:
        python -m asc.orchestrator.daemon
    """

    logging.basicConfig(level=os.environ.get("AUTOSCRIBE_LOG_LEVEL", "INFO"))
    run_forever()


__all__ = ["OrchestratorRunReport", "main", "run_forever", "run_once"]
