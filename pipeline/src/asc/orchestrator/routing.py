from __future__ import annotations

from asc.orchestrator.errors import OrchestratorContractError, ScrivenerContractError
from asc.orchestrator.queues import enqueue_worker as default_enqueue_step


def default_next_step_key(call_identity: str, next_step_number: int) -> None:
    """Deprecated compatibility shim.

    Runtime step keys are no longer the routing primitive.  The mutable
    call_state carries the current plan step and is the only queue payload.
    """

    return None


NextStepKeyLookup = object
StepQueueEnqueue = object

__all__ = [
    "OrchestratorContractError",
    "ScrivenerContractError",
    "default_enqueue_step",
    "default_next_step_key",
    "NextStepKeyLookup",
    "StepQueueEnqueue",
]
