"""Public inbox contract for the orchestrator.

The orchestrator inbox carries Redis keys only. The key kind selects the
handler. The handler loads the posted record and reads model fields to decide
what happened and how routing should continue.

Runtime state is orchestrator-owned. Enqueuer posts call keys; workers and
scrivener post notices. Cursor and results-index mutation stays inside
orchestrator handlers.
"""


CALL = "call"
RESPONSE = "response"
COMMITTED = "committed"
FAILURE = "failure"

ORCHESTRATOR_POST_KINDS = frozenset({CALL, RESPONSE, COMMITTED, FAILURE})

SCRIVENER_WRITE_CALL = "write_call"
SCRIVENER_WRITE_STEP = "write_step"
SCRIVENER_CALL_COMPLETED = "call_completed"
SCRIVENER_CALL_FAILED = "call_failed"

WORKER_EXECUTE_STEP = "execute_step"

__all__ = [
    "CALL",
    "COMMITTED",
    "FAILURE",
    "ORCHESTRATOR_POST_KINDS",
    "RESPONSE",
    "SCRIVENER_CALL_COMPLETED",
    "SCRIVENER_CALL_FAILED",
    "SCRIVENER_WRITE_CALL",
    "SCRIVENER_WRITE_STEP",
    "WORKER_EXECUTE_STEP",
]
