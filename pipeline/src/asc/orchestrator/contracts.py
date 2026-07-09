"""Public contracts for orchestrator task routing."""

CALL = "call"
OUTCOME = "outcome"
ORCHESTRATOR_POST_KINDS = frozenset({CALL, OUTCOME})

SCRIVENER_WRITE_CALL = "write_call"
SCRIVENER_CALL_COMPLETED = "call_completed"
SCRIVENER_CALL_FAILED = "call_failed"
SCRIVENER_CONFIRM_EXPORT = "confirm_export"

WORKER_EXECUTE_STEP = "execute_step"

__all__ = [
    "CALL",
    "OUTCOME",
    "ORCHESTRATOR_POST_KINDS",
    "SCRIVENER_CALL_COMPLETED",
    "SCRIVENER_CALL_FAILED",
    "SCRIVENER_CONFIRM_EXPORT",
    "SCRIVENER_WRITE_CALL",
    "WORKER_EXECUTE_STEP",
]
