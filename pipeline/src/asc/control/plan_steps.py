from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from asc.models.control.plan import PlanRecord
from asc.models.control.step import PlanStepRecord
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

    step_keys: list[str] = []
    for step_number, step in enumerate(plan.steps, start=1):
        step_record = PlanStepRecord.from_step(
            plan_identity=plan.identity,
            plan_slug=plan.record_identity,
            step_number=step_number,
            step=step,
        )
        step_keys.append(step_record.save())

    SlugMap().set(plan.record_identity, plan_key)
    return UploadedPlan(plan=plan, plan_key=plan_key, step_keys=tuple(step_keys))


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


__all__ = [
    "UploadedPlan",
    "load_plan_step_definitions",
    "upload_plan_record",
]