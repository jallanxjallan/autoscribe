from __future__ import annotations

from typing import Any

from asc.models.runtime.scrivener import ScrivenerFailure, ScrivenerResult


def is_scrivener_failure(outcome: Any) -> bool:
    return isinstance(outcome, ScrivenerFailure) or getattr(outcome, "type", "") == "scrivener_failure"


def is_scrivener_result(outcome: Any) -> bool:
    return isinstance(outcome, ScrivenerResult) or getattr(outcome, "type", "") == "scrivener_result"


def describe_scrivener_failure(outcome: Any) -> str:
    action = getattr(outcome, "action", "<unknown>")
    reason = getattr(outcome, "failure_reason", "")
    message = getattr(outcome, "fail_message", "")
    if reason and message:
        return f"scrivener {action} failed: {reason}: {message}"
    if message:
        return f"scrivener {action} failed: {message}"
    return f"scrivener {action} failed"


__all__ = [
    "describe_scrivener_failure",
    "is_scrivener_failure",
    "is_scrivener_result",
]
