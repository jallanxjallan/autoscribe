from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class InfrastructureRetryDecision:
    should_retry: bool
    delay_seconds: float = 0.0
    reason: str = ""


def decide_infrastructure_retry(
    *, attempt: int = 0, error: BaseException | None = None
) -> InfrastructureRetryDecision:
    return InfrastructureRetryDecision(
        should_retry=True,
        delay_seconds=0.25 if attempt else 0.0,
        reason=str(error) if error is not None else "orchestrator infrastructure failure",
    )
