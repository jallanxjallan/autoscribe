from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from asc.models.control.plan import PlanRecord
from asc.models.control.step import PlanStepRecord
from asc.redis.key import RedisKey
from asc.state.slugmap import SlugMap


@dataclass(frozen=True, slots=True)
class UploadedPlan:
    plan: PlanRecord
    plan_key: str
    step_keys: tuple[str, ...]

    @property
    def step_count(self) -> int:
        return len(self.step_keys)


def upload_plan_record(
    record: Mapping[str, Any],
    *,
    slugmap: object | None = None,
) -> UploadedPlan:
    plan = PlanRecord.model_validate(dict(record))
    if not plan.steps:
        raise ValueError("plan must include at least one executable step")

    plan_key = plan.save()
    step_keys = ensure_plan_step_records(plan_key, plan=plan)

    SlugMap().set(plan.record_identity, plan_key)
    return UploadedPlan(plan=plan, plan_key=plan_key, step_keys=step_keys)


def ensure_plan_step_records(
    plan_key: str,
    *,
    plan: PlanRecord | None = None,
) -> tuple[str, ...]:
    """Ensure Redis step records exist for every step in a stored plan.

    Plan upload and enqueue can now be decoupled: upload stores the plan record,
    while enqueue may be the first code path that needs concrete step keys.  This
    function is intentionally idempotent.  If any expected step key is missing, it
    materializes the step records from the submitted plan definition.
    """

    plan_identity = _identity_from_plan_key(plan_key)
    plan_record = plan or PlanRecord.load(plan_key)

    if not plan_record.steps:
        raise ValueError(f"plan has no executable steps: {plan_key}")

    expected_keys = tuple(
        str(PlanStepRecord.key_for_step(plan_identity, step_number))
        for step_number, _step in enumerate(plan_record.steps, start=1)
    )

    if all(RedisKey(key).exists() for key in expected_keys):
        return expected_keys

    step_keys: list[str] = []
    for step_number, step in enumerate(plan_record.steps, start=1):
        step_record = PlanStepRecord.from_step(
            plan_identity=plan_identity,
            plan_slug=plan_record.record_identity,
            step_number=step_number,
            step=step,
        )
        step_keys.append(step_record.save())

    return tuple(step_keys)


def load_plan_step_definitions(plan_identity: str) -> list[dict[str, Any]]:
    definitions: list[dict[str, Any]] = []
    step_number = 1

    while True:
        key = str(PlanStepRecord.key_for_step(plan_identity, step_number))
        try:
            step = PlanStepRecord.load(key)
        except KeyError:
            break

        definitions.append(step.definition)
        step_number += 1

    return definitions


def _identity_from_plan_key(plan_key: str) -> str:
    parts = plan_key.strip().split(":")
    if len(parts) != 3 or not all(parts):
        raise ValueError(f"invalid plan key: {plan_key}")
    if parts[2] != "plan":
        raise ValueError(f"key kind mismatch: expected plan, got {parts[2]} ({plan_key})")
    return parts[1]


__all__ = [
    "UploadedPlan",
    "ensure_plan_step_records",
    "load_plan_step_definitions",
    "upload_plan_record",
]
