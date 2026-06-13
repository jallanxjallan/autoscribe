from __future__ import annotations

import json
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
    """Upload a plan as a fresh Redis record and make its slug current.

    Local plan JSON may contain an old ``identity`` from a previous upload.
    The upload boundary must ignore that runtime/control identity. The slug is
    the stable human-facing name; every upload receives a new Redis key.
    """

    data = dict(record)
    data.pop("identity", None)

    plan = PlanRecord.model_validate(data)
    steps = _steps_from_plan(plan)

    if not steps:
        raise ValueError("plan must include at least one executable step")

    smap = slugmap or SlugMap()
    old_key = _current_slug_key(smap, plan.record_identity)

    plan_key = plan.save()
    step_keys = ensure_plan_step_records(plan_key, plan=plan)

    smap.set(plan.record_identity, plan_key)
    _send_plan_to_pasture(old_key, replacement_key=plan_key)

    return UploadedPlan(plan=plan, plan_key=plan_key, step_keys=step_keys)


def ensure_plan_step_records(
    plan_key: str,
    *,
    plan: PlanRecord | None = None,
) -> tuple[str, ...]:
    """Ensure Redis step records exist for every step in a stored plan."""

    plan_identity = _identity_from_plan_key(plan_key)
    plan_record = plan or PlanRecord.load(plan_key)
    steps = _steps_from_plan(plan_record)

    if not steps:
        raise ValueError(f"plan has no executable steps: {plan_key}")

    expected_keys = tuple(
        str(PlanStepRecord.key_for_step(plan_identity, step_number))
        for step_number, _step in enumerate(steps, start=1)
    )

    if all(RedisKey(key).exists() for key in expected_keys):
        return expected_keys

    step_keys: list[str] = []
    for step_number, step in enumerate(steps, start=1):
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
        except (KeyError, RuntimeError):
            break

        definitions.append(step.definition)
        step_number += 1

    return definitions


def _steps_from_plan(plan: PlanRecord) -> list[dict[str, Any]]:
    if plan.steps:
        return [dict(step) for step in plan.steps]

    raw_steps = getattr(plan, "steps_json", "") or "[]"
    parsed = json.loads(raw_steps)

    if not isinstance(parsed, list):
        raise ValueError("plan steps_json must contain a list")

    steps: list[dict[str, Any]] = []
    for index, item in enumerate(parsed, start=1):
        if not isinstance(item, Mapping):
            raise ValueError(f"plan steps_json[{index}] must be an object")
        steps.append(dict(item))

    return steps


def _current_slug_key(slugmap: object, slug: str) -> str | None:
    for method_name in ("get", "resolve", "resolve_key", "get_key", "lookup_key"):
        method = getattr(slugmap, method_name, None)
        if not callable(method):
            continue
        try:
            value = method(slug, expected_kind="plan")
        except TypeError:
            try:
                value = method(slug)
            except Exception:
                continue
        except Exception:
            continue
        return str(value) if value else None
    return None


def _send_plan_to_pasture(
    old_key: str | None,
    *,
    replacement_key: str,
    ttl_seconds: int = 60 * 60 * 24 * 7,
) -> None:
    if not old_key or old_key == replacement_key:
        return

    old_plan = RedisKey(old_key)
    if old_plan.exists():
        old_plan.expire(ttl_seconds)

    try:
        old_identity = _identity_from_plan_key(old_key)
    except ValueError:
        return

    step_number = 1
    while True:
        step_key = str(PlanStepRecord.key_for_step(old_identity, step_number))
        redis_key = RedisKey(step_key)
        if not redis_key.exists():
            break
        redis_key.expire(ttl_seconds)
        step_number += 1


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
