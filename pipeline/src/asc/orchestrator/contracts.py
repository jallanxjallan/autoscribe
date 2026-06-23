"""Public contracts for orchestrator routing."""

CALL = "call"
COMMITTED = "committed"
OUTCOME = "outcome"
RESPONSE = "response"
FAILURE = "failure"

ORCHESTRATOR_POST_KINDS = frozenset(
    {
        CALL,
        COMMITTED,
        OUTCOME,
        RESPONSE,
        FAILURE,
    }
)

SCRIVENER_WRITE_CALL = "write_call"
SCRIVENER_WRITE_STEP = "write_step"
SCRIVENER_CALL_COMPLETED = "call_completed"
SCRIVENER_CALL_FAILED = "call_failed"

WORKER_EXECUTE_STEP = "execute_step"

__all__ = [
    "CALL",
    "COMMITTED",
    "OUTCOME",
    "RESPONSE",
    "FAILURE",
    "ORCHESTRATOR_POST_KINDS",
    "SCRIVENER_CALL_COMPLETED",
    "SCRIVENER_CALL_FAILED",
    "SCRIVENER_WRITE_CALL",
    "SCRIVENER_WRITE_STEP",
    "WORKER_EXECUTE_STEP",
]
