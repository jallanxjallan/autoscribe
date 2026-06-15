from __future__ import annotations

from asc.enqueuer.keys import ResolvedEnqueueKeys
from asc.enqueuer.plan_steps import MaterializedPlanStep
from asc.enqueuer.response_index import create_response_index_from_plan_steps
from asc.models.runtime.cursor import RuntimeCursor


INITIAL_CURSOR_ACTION = "call_started"
INITIAL_CURSOR_STATUS = "pending"


def build_runtime_cursor(
    keys: ResolvedEnqueueKeys,
    *,
    plan_steps: tuple[MaterializedPlanStep, ...],
) -> RuntimeCursor:
    response_index_key = create_response_index_from_plan_steps(
        identity=keys.call_identity,
        call_key=keys.call_key,
        plan_steps=plan_steps,
    )

    return _runtime_cursor(
        identity=keys.call_identity,
        call_key=keys.call_key,
        plan_key=keys.plan_key,
        response_index_key=response_index_key,
    )


def save_runtime_cursor(cursor: RuntimeCursor) -> str:
    cursor.save()
    return str(cursor.redis_key)


def _runtime_cursor(
    *,
    identity: str,
    call_key: str,
    plan_key: str,
    response_index_key: str,
) -> RuntimeCursor:
    kwargs = dict(
        identity=identity,
        call_key=call_key,
        plan_key=plan_key,
    )
    return RuntimeCursor(**kwargs)
    


__all__ = [
    "INITIAL_CURSOR_ACTION",
    "INITIAL_CURSOR_STATUS",
    "build_runtime_cursor",
    "save_runtime_cursor",
]
