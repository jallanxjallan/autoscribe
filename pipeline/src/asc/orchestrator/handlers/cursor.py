"""Legacy cursor notices are no longer part of the orchestrator contract.

Enqueuer now posts ``call:<identity>``. The call handler creates the cursor,
materializes plan steps, and schedules the initial Scrivener write.
"""

from ..errors import OrchestratorContractError


def handle(key: object) -> None:
    identity = getattr(key, "identity", str(key))
    raise OrchestratorContractError(
        f"cursor notices are no longer accepted; post call:{identity} instead"
    )


__all__ = ["handle"]
