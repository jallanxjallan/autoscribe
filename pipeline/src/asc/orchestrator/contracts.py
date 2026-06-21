"""Public queue contract for the orchestrator.

The orchestrator queue carries Redis keys only.  The key kind selects the
handler; the identity is the call/process identity; the suffix is interpreted by
that handler and verified against canonical state before routing continues.

The orchestrator owns only its queue.  It may read cursor, plan, results-index,
and failure state to make routing decisions, but it does not create or mutate
those objects.
"""

from __future__ import annotations

CURSOR = "cursor"
RESPONSE = "response"
COMMITTED = "committed"
FAILURE = "failure"

ORCHESTRATOR_POST_KINDS = frozenset({CURSOR, RESPONSE, COMMITTED, FAILURE})

COMMITTED_CALL_SUFFIX = "call"
COMMITTED_COMPLETED_SUFFIX = "completed"
COMMITTED_FAILED_SUFFIX = "failed"
COMMITTED_STEP_PREFIX = "step."

SCRIVENER_WRITE_CALL = "write_call"
SCRIVENER_WRITE_STEP = "write_step"
SCRIVENER_CALL_COMPLETED = "call_completed"
SCRIVENER_CALL_FAILED = "call_failed"

WORKER_EXECUTE_STEP = "execute_step"

__all__ = [
    "COMMITTED",
    "COMMITTED_CALL_SUFFIX",
    "COMMITTED_COMPLETED_SUFFIX",
    "COMMITTED_FAILED_SUFFIX",
    "COMMITTED_STEP_PREFIX",
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
