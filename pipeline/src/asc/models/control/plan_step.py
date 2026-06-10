from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, ClassVar, Literal

from pydantic import ConfigDict, Field, field_validator

from asc.models.helpers.plain import positive_int, redis_key_segment_text
from asc.models.helpers.upload import RecordIdentity, json_blob
from asc.redis.key import RedisKey
from asc.redis.model_base import RedisModel


class PlanStepRecord(RedisModel):
    """Compiled reusable control step belonging to an uploaded plan."""

    namespace: ClassVar[str] = "control"
    domain: ClassVar[str] = namespace
    kind: ClassVar[str] = "plan-step"

    model_config = ConfigDict(extra="forbid")

    type: Literal["plan-step"] = "plan-step"
    identity: str
    plan_identity: str
    plan_slug: RecordIdentity
    step_number: int = Field(ge=1)
    definition_json: str

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
        return json_blob(value, "definition_json")

    @classmethod
    def from_definition(
        cls,
        *,
        plan_identity: str,
        plan_slug: str,
        step_number: int,
        definition: Mapping[str, Any],
    ) -> "PlanStepRecord":
        step_number = positive_int(step_number, "step_number")
        return cls(
            identity=f"{redis_key_segment_text(plan_identity, 'plan_identity')}.{step_number}",
            plan_identity=plan_identity,
            plan_slug=plan_slug,
            step_number=step_number,
            definition_json=dict(definition),
        )

    @property
    def definition(self) -> dict[str, Any]:
        parsed = json.loads(self.definition_json or "{}")
        if not isinstance(parsed, dict):
            raise ValueError("definition_json must contain a JSON object")
        return parsed

    @classmethod
    def key_for_step(cls, plan_identity: str, step_number: int) -> RedisKey:
        return RedisKey.from_parts(
            cls.domain,
            redis_key_segment_text(plan_identity, "plan_identity"),
            f"{cls.kind}.{positive_int(step_number, 'step_number')}",
        )

    @classmethod
    def key_for_identity(cls, identity: str) -> RedisKey:
        raise TypeError("PlanStepRecord requires step_number; use key_for_step(plan_identity, step_number)")

    @property
    def redis_key(self) -> RedisKey:
        return self.key_for_step(self.plan_identity, self.step_number)


__all__ = ["PlanStepRecord"]
