"""Legacy cursor notices are no longer part of the public orchestrator contract.

Enqueuer now posts ``call:<identity>``. The call handler creates the cursor and
results index inside orchestrator-owned runtime state.
"""

from ..errors import OrchestratorContractError


def handle(identity: str) -> None:
    raise OrchestratorContractError(
        f"cursor notices are no longer accepted; post call:{identity} instead"
    )


__all__ = ["handle"]
