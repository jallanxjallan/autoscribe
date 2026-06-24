"""Plan materialization helpers for orchestrator index handling.

These functions compile Plan step definitions into short-lived Step records and
place those Step keys in the index. They do not create worker Tasks; worker task
construction lives in ``tasks.worker``.
"""

from __future__ import annotations

import json
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
    """Compile one plan step into a short-lived Step record."""

    raw_step = plan.step_definition(step_number)
    args = plan.step_args(step_number)
    data: dict[str, Any] = {**raw_step, **args}

    data.update(
        {
            "identity": step_identity(str(plan.identity), step_number),
            "plan_identity": str(plan.identity),
            "step_number": step_number,
            "executor": step_executor_key(plan, step_number),
            "action": step_action_key(data, plan, step_number),
            "instructions_json": json.dumps(
                step_instruction_keys(data),
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            "args_json": json.dumps(
                args,
                ensure_ascii=False,
                separators=(",", ":"),
                default=str,
            ),
            "ttl_seconds": ttl_seconds,
        }
    )
    return Step(**data)


def step_identity(plan_identity: str, step_number: int) -> str:
    return f"{plan_identity}.{step_number}"


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


def step_instruction_keys(step: dict[str, Any]) -> list[str]:
    values: list[str] = []

    for name in ("instruction_keys", "instruction_slugs", "instructions"):
        values.extend(str(value) for value in step.get(name, []))

    return list(dict.fromkeys(values))


__all__ = [
    "make_step_record",
    "materialize_plan_steps",
    "plan_step_count",
    "plan_steps",
    "step_action_key",
    "step_executor_key",
    "step_identity",
    "step_instruction_keys",
]
