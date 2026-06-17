"""One-shot runtime API for the orchestrator."""

from __future__ import annotations

from dataclasses import dataclass

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
    claimed = build_service().run_once(timeout=timeout, empty_limit=empty_limit, wait=wait)
    return OrchestratorRunReport(claimed=claimed)


__all__ = ["OrchestratorRunReport", "run_once"]
