from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RetryDecision:
    """Decision returned when orchestrator error policy is expanded."""

    should_retry: bool
    delay_seconds: float = 0.0
    reason: str = ""


def decide_retry(*, attempt: int = 0, error: BaseException | None = None) -> RetryDecision:
    """Return the retry policy for an orchestrator-side processing error.

    Stub for now. This is where backoff windows, maximum attempts, and error
    classification should live once retry policy becomes explicit.
    """

    return RetryDecision(
        should_retry=True,
        delay_seconds=0.0,
        reason=str(error) if error is not None else "orchestrator processing failed",
    )
