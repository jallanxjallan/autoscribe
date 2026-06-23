"""Legacy top-level orchestrator handler.

The public orchestrator inbox now accepts only call:<identity> and
outcome:<identity>. This module is intentionally not imported by
orchestrator.handlers.HANDLERS. Keep it only as a short-term reference while
the old committed/response/failure/cursor message kinds are removed.
"""

"""Legacy cursor notices are no longer part of the public orchestrator contract.

Enqueuer now posts ``call:<identity>``. The call handler creates the cursor and
results index inside orchestrator-owned runtime state.
"""

from ..errors import OrchestratorContractError


def handle(key: object) -> None:
    identity = getattr(key, "identity", str(key))
    raise OrchestratorContractError(
        f"cursor notices are no longer accepted; post call:{identity} instead"
    )


__all__ = ["handle"]
