from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from asc.models.control.plan import Plan


def load_runnable_plan_step_count(plan_key: str) -> int:
    """Load a plan and return its step count.

    Enqueuer only proves that a plan has at least one step. It does not
    materialize step records or interpret step content; that belongs downstream
    to the orchestrator/worker path.
    """

    plan = Plan.load(plan_key)
    steps = getattr(plan, "steps", None)
    if not _is_step_sequence(steps):
        raise ValueError(f"plan steps must be a list: {plan_key}")

    step_count = len(steps)
    if step_count < 1:
        raise ValueError(f"plan has no steps: {plan_key}")
    return step_count


def _is_step_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


__all__ = ["load_runnable_plan_step_count"]
