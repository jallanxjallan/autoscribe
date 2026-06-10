from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InfrastructureRetryDecision:
    """Retry decision for orchestrator infrastructure failures only.

    Call/LLM/script retries belong to the worker's scoped responsibility.  The
    orchestrator sees a business failure only after the worker has exhausted
    the policy attached to the current plan step and returned the call_state as
    terminally failed.
    """

    should_retry: bool
    delay_seconds: float = 0.0
    reason: str = ""


def decide_infrastructure_retry(
    *, attempt: int = 0, error: BaseException | None = None
) -> InfrastructureRetryDecision:
    return InfrastructureRetryDecision(
        should_retry=True,
        delay_seconds=0.0,
        reason=str(error) if error is not None else "orchestrator infrastructure failure",
    )


# Backward-compatible name for old imports.  This must not be used for worker
# task retries; it is only an infrastructure requeue decision.
def decide_retry(*, attempt: int = 0, error: BaseException | None = None) -> InfrastructureRetryDecision:
    return decide_infrastructure_retry(attempt=attempt, error=error)
