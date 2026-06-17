from __future__ import annotations

from typing import Any


def is_scrivener_failure(outcome: Any) -> bool:
    return getattr(outcome, "type", "") == "scrivener_failure" or getattr(outcome, "kind", "") in {
        "scrivener_failure",
        "failure",
    }


def is_scrivener_result(outcome: Any) -> bool:
    return getattr(outcome, "type", "") == "scrivener_result" or getattr(outcome, "kind", "") in {
        "scrivener_result",
        "result",
    }


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
