from __future__ import annotations

from asc.models.runtime.step import RuntimeStepRecord
from asc.orchestrator.queues import enqueue_worker
from asc.orchestrator.state import (
    call_identity,
    current_step_number,
    save_call_state,
    set_current_step_number,
    set_worker_keys,
)
from asc.orchestrator.verify import verify_input_artifact


def advance_call_state(call_state, call_state_key: str) -> bool:
    """Advance to the next already-materialized runtime step.

    The plan master is not consulted here. Enqueue has already materialized the
    runtime:<ULID>:step.<n> records. Terminal state is determined only by the
    absence of the next materialized step record.
    """

    identity = call_identity(call_state)
    next_step_number = current_step_number(call_state) + 1
    next_step_key = runtime_step_key(identity, next_step_number)

    if not materialized_step_exists(next_step_key):
        return False

    set_current_step_number(call_state, next_step_number)
    set_worker_keys(
        call_state,
        step_key=next_step_key,
        response_key=runtime_content_key(identity, next_step_number),
    )
    verify_input_artifact(call_state)
    save_call_state(call_state)
    enqueue_worker(call_state_key)
    return True


def materialized_step_exists(step_key: str) -> bool:
    try:
        RuntimeStepRecord.load(step_key)
    except KeyError:
        return False
    return True


def runtime_step_key(identity: str, step_number: int) -> str:
    return f"runtime:{identity}:step.{step_number}"


def runtime_content_key(identity: str, position: int) -> str:
    return f"runtime:{identity}:content.{position}"
