from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, ClassVar, Literal

from pydantic import ConfigDict, Field, field_validator

from asc.models.helpers.plain import positive_int, redis_key_segment_text
from asc.models.helpers.upload import RecordIdentity
from asc.redis.key import RedisKey
from asc.redis.model_base import RedisModel


class PlanStepRecord(RedisModel):
    """Trusted immutable executable step belonging to an uploaded plan."""

    namespace: ClassVar[str] = "control"
    domain: ClassVar[str] = namespace
    kind: ClassVar[str] = "plan-step"

    model_config = ConfigDict(extra="forbid")

    type: Literal["plan-step"] = "plan-step"
    identity: str
    plan_identity: str
    plan_slug: RecordIdentity
    step_number: int = Field(ge=1)
    definition_json: str = "{}"

    @field_validator("identity", "plan_identity", mode="before")
    @classmethod
    def validate_identity(cls, value: object) -> str:
        return redis_key_segment_text(value, "identity")

    @field_validator("step_number", mode="before")
    @classmethod
    def validate_step_number(cls, value: object) -> int:
        return positive_int(value, "step_number")

    @field_validator("definition_json", mode="before")
    @classmethod
    def validate_definition_json(cls, value: object) -> str:
        if value is None:
            return "{}"
        if isinstance(value, str):
            return value
        if isinstance(value, Mapping):
            return json.dumps(dict(value), ensure_ascii=False, separators=(",", ":"))
        raise ValueError("definition_json must be a JSON string or object")

    @classmethod
    def from_step(
        cls,
        *,
        plan_identity: str,
        plan_slug: str,
        step_number: int,
        step: object,
    ) -> "PlanStepRecord":
        if not isinstance(step, Mapping):
            raise ValueError("plan step must be an object")

        step_number = positive_int(step_number, "step_number")
        normalized_plan_identity = redis_key_segment_text(plan_identity, "plan_identity")
        definition = _execution_definition(step, step_number=step_number)

        return cls(
            identity=f"{normalized_plan_identity}.{step_number}",
            plan_identity=normalized_plan_identity,
            plan_slug=plan_slug,
            step_number=step_number,
            definition_json=definition,
        )

    @property
    def definition(self) -> dict[str, Any]:
        value = json.loads(self.definition_json or "{}")
        if not isinstance(value, dict):
            raise ValueError("plan step definition_json must decode to an object")
        return value

    @classmethod
    def key_for_step(cls, plan_identity: str, step_number: int) -> RedisKey:
        return RedisKey.from_parts(
            cls.domain,
            redis_key_segment_text(plan_identity, "plan_identity"),
            f"{cls.kind}.{positive_int(step_number, 'step_number')}",
        )

    @classmethod
    def key_for_identity(cls, identity: str) -> RedisKey:
        raise TypeError(
            "PlanStepRecord requires step_number; use key_for_step(plan_identity, step_number)"
        )

    @property
    def redis_key(self) -> RedisKey:
        return self.key_for_step(self.plan_identity, self.step_number)


def _execution_definition(step: Mapping[str, Any], *, step_number: int) -> dict[str, Any]:
    args = dict(step.get("args") or {})

    engine = args.get("engine")
    script = args.get("script")

    engine_record = step.get("engine")
    if not engine and isinstance(engine_record, Mapping):
        engine = engine_record.get("key") or engine_record.get("module")

    script_record = step.get("script")
    if not script and isinstance(script_record, Mapping):
        script = script_record.get("key") or script_record.get("module")

    definition: dict[str, Any] = {
        "index": step_number,
        "kind": step.get("kind", ""),
        "label": step.get("label", ""),
        "instructions": list(step.get("instructions") or []),
        "args": args,
    }

    if engine:
        args["engine"] = engine
    if script:
        args["script"] = script

    return definition


__all__ = ["PlanStepRecord"]