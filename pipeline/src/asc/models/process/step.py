"""Short-lived executable step records."""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import ConfigDict, Field, field_serializer, field_validator, model_validator

from asc.core.identity import generate_identity
from asc.core.timestamp import timestamp
from asc.models.helpers.plain import redis_key_segment_text
from asc.redis.message_base import RedisMessage


class Step(RedisMessage):
    """Materialized worker instruction for one plan step.

    A Step is the compiled runtime form of one plan step. It is reusable across
    calls. Workers receive the Step key plus whatever call/data key is carried
    by the WorkerTask.

    Step keys use the Plan identity plus the numeric step suffix:

        step:<plan_identity>:<step_number>

    The step number is stored as data. The suffix exists only so the inherited
    Redis key machinery can build the three-segment Step key.
    """

    model_config = ConfigDict(extra="forbid")

    kind: ClassVar[str] = "step"

    identity: str = Field(default_factory=generate_identity)
    suffix: str = Field(default="", exclude=True)

    step_number: int
    engine: str
    step_json: dict[str, Any]

    created_at: int = Field(default_factory=timestamp)

    @model_validator(mode="after")
    def set_suffix_from_step_number(self) -> "Step":
        Step.suffix = str(self.step_number)
        return self

    @field_validator("identity", mode="before")
    @classmethod
    def validate_identity(cls, value: object) -> str:
        return redis_key_segment_text(value, "identity")

    @field_validator("engine", mode="before")
    @classmethod
    def validate_engine(cls, value: object) -> str:
        text = "" if value is None else str(value).strip()
        if not text:
            raise ValueError("engine must be non-empty")
        return text

    @field_validator("step_number", mode="before")
    @classmethod
    def validate_step_number(cls, value: object) -> int:
        number = int(value)
        if number < 1:
            raise ValueError("step_number must be >= 1")
        return number

    @field_serializer("created_at", "step_number")
    def serialize_ints(self, value: int) -> str:
        return str(value)


__all__ = ["Step"]