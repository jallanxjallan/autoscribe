"""Short-lived executable step records."""

from __future__ import annotations

from typing import Any, ClassVar, Self

from pydantic import ConfigDict, Field, field_serializer

from asc.core.identity import generate_identity
from asc.core.timestamp import timestamp
from asc.redis.message_base import RedisMessage


class Step(RedisMessage):
    """Materialized worker instruction for one plan step.

    A Step is the compiled runtime form of one plan step. It is reusable across
    calls. Workers receive the Step key plus whatever call/data key is carried
    by the WorkerTask.

    Step keys use the Plan identity plus the numeric step suffix:

        step:<plan_identity>:<step_number>

    Only ``step_number`` and ``engine`` are part of the contract. Everything
    else from the plan step is kept as first-class Redis hash fields and passed
    through to the worker engine as runtime arguments.
    """

    model_config = ConfigDict(extra="allow")

    kind: ClassVar[str] = "step"
    suffix: ClassVar[str] = ""

    identity: str = Field(default_factory=generate_identity)
    step_number: int
    engine: str
    created_at: int = Field(default_factory=timestamp)


    def model_post_init(self, __context: Any) -> None:
        Step.suffix = str(self.step_number)

    @field_serializer("created_at", "step_number")
    def serialize_ints(self, value: int) -> str:
        return str(value)


__all__ = ["Step"]
