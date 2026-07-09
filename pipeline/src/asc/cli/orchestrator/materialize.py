"""Plan materialization helpers for orchestrator index handling.

These functions compile Plan step definitions into short-lived Step records and
place those Step keys in the index. They do not create worker Tasks; worker task
construction lives in ``tasks.worker``.
"""

from __future__ import annotations

from typing import Any

from asc.models.process.step import Step


def materialize_plan_steps(
    *,
    plan: Any,
    index: Any,
    ttl_seconds: int | None = None,
) -> list[str]:
    """Save Step records for every Plan step and put their keys in the index."""

    step_keys: list[str] = []

    for step_number in range(1, plan_step_count(plan) + 1):
        step = make_step_record(
            plan=plan,
            step_number=step_number,
            ttl_seconds=ttl_seconds,
        )
        step.save()
        index.set_slot(step_number, step.raw_key)
        step_keys.append(step.raw_key)

    return step_keys


def make_step_record(
    *,
    plan: Any,
    step_number: int,
    ttl_seconds: int | None = None,
) -> Step:
    """Compile one plan step into a flat, short-lived Step record."""

    data: dict[str, Any] = {
        **plan.step_definition(step_number),
        **plan.step_args(step_number),
        "identity": str(plan.identity),
        "ordinal": str(step_number),
        "engine": plan.step_engine(step_number),
    }

    if ttl_seconds is not None:
        data["ttl_seconds"] = ttl_seconds

    return Step(**data)


def plan_step_count(plan: Any) -> int:
    return plan.total_steps


def plan_steps(plan: Any) -> list[dict[str, Any]]:
    return list(plan.steps)


def step_executor_key(plan: Any, step_number: int) -> str:
    return plan.step_engine(step_number).removeprefix("engines.").replace("-", "_")


def step_action_key(step: dict[str, Any], plan: Any, step_number: int) -> str:
    return str(
        step.get("action")
        or step.get("handler")
        or step.get("script")
        or step.get("model")
        or step_executor_key(plan, step_number)
    )


__all__ = [
    "make_step_record",
    "materialize_plan_steps",
    "plan_step_count",
    "plan_steps",
    "step_action_key",
    "step_executor_key",
]
