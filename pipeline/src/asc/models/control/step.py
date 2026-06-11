from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import ConfigDict, Field, field_validator

from asc.models.helpers.plain import positive_int, redis_key_segment_text
from asc.models.helpers.upload import RecordIdentity
from asc.redis.key import RedisKey
from asc.redis.model_base import RedisModel


_RESERVED_FIELDS = {
    "type",
    "identity",
    "plan_identity",
    "plan_slug",
    "step_number",
}


class PlanStepRecord(RedisModel):
    """Trusted immutable control step belonging to an uploaded plan."""

    namespace: ClassVar[str] = "control"
    domain: ClassVar[str] = namespace
    kind: ClassVar[str] = "plan-step"

    model_config = ConfigDict(extra="allow")

    type: Literal["plan-step"] = "plan-step"
    identity: str
    plan_identity: str
    plan_slug: RecordIdentity
    step_number: int = Field(ge=1)

    @field_validator("identity", "plan_identity", mode="before")
    @classmethod
    def validate_identity(cls, value: object) -> str:
        return redis_key_segment_text(value, "identity")

    @field_validator("step_number", mode="before")
    @classmethod
    def validate_step_number(cls, value: object) -> int:
        return positive_int(value, "step_number")

    @classmethod
    def from_step(
        cls,
        *,
        plan_identity: str,
        plan_slug: str,
        step_number: int,
        step: object,
    ) -> "PlanStepRecord":
        if not isinstance(step, dict):
            raise ValueError("plan step must be an object")

        payload = dict(step)
        for field in _RESERVED_FIELDS:
            payload.pop(field, None)

        step_number = positive_int(step_number, "step_number")
        return cls(
            identity=f"{redis_key_segment_text(plan_identity, 'plan_identity')}.{step_number}",
            plan_identity=plan_identity,
            plan_slug=plan_slug,
            step_number=step_number,
            **payload,
        )

    @property
    def definition(self) -> dict[str, Any]:
        data = self.model_dump(mode="json")
        return {
            key: value
            for key, value in data.items()
            if key not in _RESERVED_FIELDS
        }

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


__all__ = ["PlanStepRecord"]