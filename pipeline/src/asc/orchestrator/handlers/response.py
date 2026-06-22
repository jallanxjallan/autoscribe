"""Legacy top-level orchestrator handler.

The public orchestrator inbox now accepts only call:<identity> and
outcome:<identity>. This module is intentionally not imported by
orchestrator.handlers.HANDLERS. Keep it only as a short-term reference while
the old committed/response/failure/cursor message kinds are removed.
"""

"""Handle worker response notices.

Worker response routing is parked while the smoke target is limited to:
    orchestrator -> scrivener -> orchestrator

Re-enable this module when the generic worker Task/Outcome shape is wired in.
"""

from ..errors import OrchestratorContractError


def handle(identity: str) -> None:
    raise OrchestratorContractError(
        f"worker response notices are parked for this smoke cycle: response:{identity}"
    )


__all__ = ["handle"]
