from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from asc.models.control.plan import PlanRecord


def terminal_step_for_plan(plan_key: str) -> int:
    """Return the highest declared step index for a plan.

    In this codebase, ``index`` means position in a list/array. The cursor stores
    this immutable terminal position when the call is enqueued, avoiding repeated
    plan inspection during outcome handling.
    """
    plan = PlanRecord.load(plan_key)
    steps = _plan_steps(plan)

    indexes = [_step_index(step) for step in steps]
    indexes = [index for index in indexes if index is not None]

    if not indexes:
        raise ValueError(f"plan has no indexed steps: {plan_key}")

    return max(indexes)


def _plan_steps(plan: Any) -> Sequence[Any]:
    steps = getattr(plan, "steps", None)
    if steps is not None:
        return steps

    record_content = getattr(plan, "record_content", None)
    if isinstance(record_content, Mapping):
        steps = record_content.get("steps")
        if steps is not None:
            return steps

    raw_record = getattr(plan, "raw_record", None)
    if isinstance(raw_record, Mapping):
        steps = raw_record.get("steps")
        if steps is not None:
            return steps

    raise ValueError(f"plan does not expose steps: {getattr(plan, 'redis_key', '<unknown>')}")


def _step_index(step: Any) -> int | None:
    if isinstance(step, Mapping):
        value = step.get("index")
    else:
        value = getattr(step, "index", None)

    try:
        index = int(str(value))
    except (TypeError, ValueError):
        return None

    if index < 1:
        return None
    return index


__all__ = ["terminal_step_for_plan"]
