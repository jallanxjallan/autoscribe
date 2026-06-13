from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, ClassVar, Literal

from pydantic import ConfigDict, Field, field_validator

from asc.models.helpers.plain import plain_non_empty_string, positive_int, redis_key_segment_text
from asc.models.helpers.upload import RecordIdentity
from asc.redis.key import RedisKey
from asc.redis.model_base import RedisModel


class PlanStepRecord(RedisModel):
    """Trusted immutable executable step belonging to an uploaded plan.

    The engine is first-class. definition_json is the engine argument payload
    and is passed blindly to the selected engine.
    """

    namespace: ClassVar[str] = "control"
    domain: ClassVar[str] = namespace
    kind: ClassVar[str] = "plan-step"

    model_config = ConfigDict(extra="forbid")

    type: Literal["plan-step"] = "plan-step"

    identity: str
    plan_identity: str
    plan_slug: RecordIdentity
    step_number: int = Field(ge=1)

    engine: str
    definition_json: str = "{}"

    @field_validator("identity", "plan_identity", mode="before")
    @classmethod
    def validate_identity(cls, value: object) -> str:
        return redis_key_segment_text(value, "identity")

    @field_validator("step_number", mode="before")
    @classmethod
    def validate_step_number(cls, value: object) -> int:
        return positive_int(value, "step_number")

    @field_validator("engine", mode="before")
    @classmethod
    def validate_engine(cls, value: object) -> str:
        return plain_non_empty_string(value, "engine")

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

        normalized_plan_identity = redis_key_segment_text(plan_identity, "plan_identity")
        normalized_step_number = positive_int(step_number, "step_number")

        return cls(
            identity=f"{normalized_plan_identity}.{normalized_step_number}",
            plan_identity=normalized_plan_identity,
            plan_slug=plan_slug,
            step_number=normalized_step_number,
            engine=_engine(step),
            definition_json=_definition(step),
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


def _engine(step: Mapping[str, Any]) -> str:
    value = step["engine"]
    if isinstance(value, Mapping):
        value = value["key"]
    return plain_non_empty_string(value, "engine")


def _definition(step: Mapping[str, Any]) -> dict[str, Any]:
    value = step.get("definition_json")
    if value is not None:
        if isinstance(value, str):
            decoded = json.loads(value)
            if not isinstance(decoded, dict):
                raise ValueError("definition_json must decode to an object")
            return decoded
        if isinstance(value, Mapping):
            return dict(value)
        raise ValueError("definition_json must be a JSON string or object")

    return dict(step["args"])


__all__ = ["PlanStepRecord"]
