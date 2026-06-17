from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from asc.models.control.plan import Plan


@dataclass(frozen=True, slots=True)
class MaterializedPlanStep:
    step_number: int
    step: Any


def load_plan_steps(plan_key: str) -> tuple[MaterializedPlanStep, ...]:
    """Load a plan and return its validated runtime step list.

    Enqueue only confirms that steps exist and can be numbered. Terminal logic
    belongs in the orchestrator/scrivener path, not here.
    """
    plan = Plan.load(plan_key)
    raw_steps = _plan_steps(plan)
    steps = tuple(_materialize_steps(raw_steps, plan_key=plan_key))
    if not steps:
        raise ValueError(f"plan has no steps: {plan_key}")
    return steps


def _materialize_steps(
    raw_steps: Sequence[Any],
    *,
    plan_key: str,
) -> list[MaterializedPlanStep]:
    materialized: list[MaterializedPlanStep] = []
    for position, step in enumerate(raw_steps, start=1):
        step_number = _step_number(step, fallback=position)
        if step_number < 1:
            raise ValueError(f"plan has invalid step number: {plan_key} step={step!r}")
        materialized.append(MaterializedPlanStep(step_number=step_number, step=step))

    materialized.sort(key=lambda item: item.step_number)
    expected = list(range(1, len(materialized) + 1))
    actual = [item.step_number for item in materialized]
    if actual != expected:
        raise ValueError(
            f"plan steps must be contiguous from 1: {plan_key} actual={actual}"
        )
    return materialized


def _plan_steps(plan: Any) -> Sequence[Any]:
    steps = getattr(plan, "steps", None)
    if steps is not None:
        return _ensure_sequence(steps, plan)

    record_content = getattr(plan, "record_content", None)
    if isinstance(record_content, Mapping):
        steps = record_content.get("steps")
        if steps is not None:
            return _ensure_sequence(steps, plan)

    raw_record = getattr(plan, "raw_record", None)
    if isinstance(raw_record, Mapping):
        steps = raw_record.get("steps")
        if steps is not None:
            return _ensure_sequence(steps, plan)

    raise ValueError(f"plan does not expose steps: {getattr(plan, 'redis_key', '<unknown>')}")


def _ensure_sequence(value: Any, plan: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    raise ValueError(f"plan steps must be a list: {getattr(plan, 'redis_key', '<unknown>')}")


def _step_number(step: Any, *, fallback: int) -> int:
    if isinstance(step, Mapping):
        value = step.get("step_number", step.get("index", fallback))
    else:
        value = getattr(step, "step_number", getattr(step, "index", fallback))
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return int(fallback)


__all__ = ["MaterializedPlanStep", "load_plan_steps"]
