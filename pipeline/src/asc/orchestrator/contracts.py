"""Public inbox contract for the orchestrator.

The orchestrator inbox carries Redis keys only. The key kind selects the
handler. The handler loads the posted record and reads model fields to decide
what happened and how routing should continue.

The orchestrator owns only its inbox boundary. It may read cursor, plan,
results-index, committed, response, and failure records to make routing
decisions, but it should not infer operational meaning from Redis key suffixes.
"""


CURSOR = "cursor"
RESPONSE = "response"
COMMITTED = "committed"
FAILURE = "failure"

ORCHESTRATOR_POST_KINDS = frozenset({CURSOR, RESPONSE, COMMITTED, FAILURE})

SCRIVENER_WRITE_CALL = "write_call"
SCRIVENER_WRITE_STEP = "write_step"
SCRIVENER_CALL_COMPLETED = "call_completed"
SCRIVENER_CALL_FAILED = "call_failed"

WORKER_EXECUTE_STEP = "execute_step"

__all__ = [
    "COMMITTED",
    "CURSOR",
    "FAILURE",
    "ORCHESTRATOR_POST_KINDS",
    "RESPONSE",
    "SCRIVENER_CALL_COMPLETED",
    "SCRIVENER_CALL_FAILED",
    "SCRIVENER_WRITE_CALL",
    "SCRIVENER_WRITE_STEP",
    "WORKER_EXECUTE_STEP",
]