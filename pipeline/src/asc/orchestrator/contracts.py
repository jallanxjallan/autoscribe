"""Public inbox contract for the orchestrator.

The orchestrator inbox carries Redis keys only. The key kind selects the broad
message class only. Identity and suffix are opaque to the dispatcher; model
fields carry the routing semantics.

Current public kinds:
    call     start or resume orchestration for a Call record
             accepts call:<identity> and call:<identity>:record
    outcome  result of a queued Task

Task-specific routing belongs inside the outcome handler, using fields such as
package, action, and result.
"""


CALL = "call"
OUTCOME = "outcome"

ORCHESTRATOR_POST_KINDS = frozenset({CALL, OUTCOME})

SCRIVENER_WRITE_CALL = "write_call"
SCRIVENER_WRITE_STEP = "write_step"
SCRIVENER_CALL_COMPLETED = "call_completed"
SCRIVENER_CALL_FAILED = "call_failed"

WORKER_EXECUTE_STEP = "execute_step"

__all__ = [
    "CALL",
    "OUTCOME",
    "ORCHESTRATOR_POST_KINDS",
    "SCRIVENER_CALL_COMPLETED",
    "SCRIVENER_CALL_FAILED",
    "SCRIVENER_WRITE_CALL",
    "SCRIVENER_WRITE_STEP",
    "WORKER_EXECUTE_STEP",
]
