from __future__ import annotations

from asc.enqueue.keys import ResolvedEnqueueKeys
from asc.enqueue.plan_steps import terminal_step_for_plan
from asc.models.runtime.cursor import RuntimeCursor
from asc.runtime.response_index import initialize_response_index


def build_runtime_cursor(keys: ResolvedEnqueueKeys) -> RuntimeCursor:
    # The plan is inspected once at enqueue time to size the fixed response
    # index. After this, runtime progress is determined by response slots, not
    # by repeatedly loading the plan or copying terminal state into the cursor.
    terminal_step = terminal_step_for_plan(keys.plan_key)
    initialize_response_index(
        identity=keys.call_identity,
        call_key=keys.call_key,
        terminal_step=terminal_step,
    )

    return RuntimeCursor(
        identity=keys.call_identity,
        call_key=keys.call_key,
        plan_key=keys.plan_key,
        current_step=1,
    )


def save_runtime_cursor(cursor: RuntimeCursor) -> str:
    cursor.save()
    return str(cursor.redis_key)


__all__ = ["build_runtime_cursor", "save_runtime_cursor"]
