from __future__ import annotations

import inspect
from typing import Any

from asc.enqueuer.plan_steps import MaterializedPlanStep
from asc.runtime import response_index as runtime_response_index


def create_response_index_from_plan_steps(
    *,
    identity: str,
    call_key: str,
    plan_steps: tuple[MaterializedPlanStep, ...],
) -> str:
    """Create the fixed response index and place the call key in slot 0.

    This wrapper intentionally contains the compatibility glue for the evolving
    ``asc.runtime.response_index`` API. Callers should not perform Redis writes
    or know whether the backing implementation is a hash, index_base wrapper,
    or something else.
    """
    if not plan_steps:
        raise ValueError("plan_steps must not be empty")

    index_key = _initialize_index(
        identity=identity,
        call_key=call_key,
        plan_steps=plan_steps,
    )
    _insert_call_slot(index_key=index_key, identity=identity, call_key=call_key)
    return index_key


def _initialize_index(
    *,
    identity: str,
    call_key: str,
    plan_steps: tuple[MaterializedPlanStep, ...],
) -> str:
    fn = getattr(runtime_response_index, "initialize_response_index", None)
    if fn is None:
        raise RuntimeError("asc.runtime.response_index.initialize_response_index is missing")

    step_numbers = tuple(step.step_number for step in plan_steps)
    terminal_step = max(step_numbers)

    attempts = [
        dict(identity=identity, call_key=call_key, plan_steps=plan_steps),
        dict(identity=identity, call_key=call_key, steps=plan_steps),
        dict(identity=identity, call_key=call_key, step_numbers=step_numbers),
        dict(identity=identity, call_key=call_key, terminal_step=terminal_step),
    ]

    for kwargs in attempts:
        try:
            result = fn(**kwargs)
        except TypeError:
            continue
        return _index_key_from_result(result=result, identity=identity)

    raise TypeError(
        "could not call initialize_response_index with supported enqueue signatures"
    )


def _insert_call_slot(*, index_key: str, identity: str, call_key: str) -> None:
    """Ensure response slot 0 points at the immutable call key."""
    function_names = (
        "insert_response_slot",
        "set_response_slot",
        "write_response_slot",
        "set_response_index_slot",
        "put_response_slot",
    )
    for name in function_names:
        fn = getattr(runtime_response_index, name, None)
        if fn is None:
            continue
        if _call_slot_writer(fn, index_key=index_key, identity=identity, call_key=call_key):
            return

    # Older initialize_response_index(identity, call_key, terminal_step) already
    # inserted the call slot. Verify when a reader exists; otherwise fail loud.
    reader = getattr(runtime_response_index, "response_index", None)
    if reader is not None:
        slots = reader(index_key)
        if str(slots.get(0, "")).strip() == call_key:
            return

    raise RuntimeError(
        "response index API has no slot writer and slot 0 was not confirmed"
    )


def _call_slot_writer(fn: Any, *, index_key: str, identity: str, call_key: str) -> bool:
    attempts = [
        dict(index_key=index_key, slot=0, value=call_key),
        dict(index_key=index_key, step_number=0, value=call_key),
        dict(response_index_key=index_key, slot=0, value=call_key),
        dict(identity=identity, slot=0, value=call_key),
        dict(identity=identity, step_number=0, value=call_key),
        dict(index_key=index_key, slot=0, response_key=call_key),
        dict(identity=identity, slot=0, response_key=call_key),
    ]
    for kwargs in attempts:
        try:
            fn(**kwargs)
        except TypeError:
            continue
        return True
    return False


def _index_key_from_result(*, result: Any, identity: str) -> str:
    if isinstance(result, str) and result.strip():
        return result.strip()
    for name in ("response_index_key", "index_key", "redis_key", "key"):
        value = getattr(result, name, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return f"runtime:{identity}:response_index"


__all__ = ["create_response_index_from_plan_steps"]
