"""Reusable executable step control records."""

from __future__ import annotations

from typing import ClassVar

from pydantic import AliasChoices, ConfigDict, Field, field_serializer, field_validator

from asc.core.identity import generate_identity
from asc.core.timestamp import timestamp
from asc.redis.model_base import RedisModel


class Step(RedisModel):
    """Materialized worker instruction for one plan step.

    Step is a reusable control asset derived from a Plan. Workers receive the
    Step key plus whatever call/data key is carried by the WorkerTask.

    Step keys use the Plan identity plus the numeric ordinal:

        step:<plan_identity>:<ordinal>

    Only ``ordinal`` and ``engine`` are part of the contract. Everything else
    from the plan step is kept as first-class Redis hash fields and passed
    through to the worker engine as runtime arguments.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    kind: ClassVar[str] = "step"

    identity: str = Field(default_factory=generate_identity)
    ordinal: int = Field(validation_alias=AliasChoices("ordinal", "step_number"))
    engine: str
    created_at: int = Field(default_factory=timestamp)

    @property
    def step_number(self) -> int:
        """Compatibility alias while older worker/orchestrator code is migrated."""
        return self.ordinal

    @field_validator("ordinal", mode="before")
    @classmethod
    def validate_ordinal(cls, value: object) -> int:
        text = "" if value is None else str(value).strip()
        if not text:
            raise ValueError("step ordinal must not be empty")

        number = int(text)
        if number < 1:
            raise ValueError(f"step ordinal must be >= 1: {number}")

        return number

    @field_serializer("created_at", "ordinal")
    def serialize_ints(self, value: int) -> str:
        return str(value)


__all__ = ["Step"]
