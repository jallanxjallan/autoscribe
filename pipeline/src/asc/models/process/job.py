"""Persisted orchestration jobs for active calls."""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import ConfigDict, Field, field_serializer, field_validator

from asc.core.timestamp import timestamp
from asc.models.helpers.plain import redis_key_segment_text
from asc.redis.model_base import RedisModel


class Job(RedisModel):
    """One call registered for orchestration.

    The job shares the call identity, so its Redis key is deterministic:

        job:<call_identity>:record

    Runtime records are addressed separately as
    ``runtime:<call_identity>:<ordinal>``. The active-jobs sorted set contains
    this job key; its score is orchestration state rather than job data.
    """

    model_config = ConfigDict(extra="forbid")

    kind: ClassVar[str] = "job"
    component: ClassVar[Literal["record"]] = "record"

    identity: str
    plan_identity: str
    total_steps: int
    created_at: int = Field(default_factory=timestamp)

    @property
    def call_identity(self) -> str:
        return self.identity

    @field_validator("identity", "plan_identity", mode="before")
    @classmethod
    def validate_identity(cls, value: object) -> str:
        return redis_key_segment_text(value, "identity")

    @field_validator("total_steps", mode="before")
    @classmethod
    def validate_total_steps(cls, value: object) -> int:
        total_steps = int(value)
        if total_steps < 1:
            raise ValueError("job total_steps must be positive")
        return total_steps

    @field_serializer("created_at", "total_steps")
    def serialize_int(self, value: int) -> str:
        return str(value)


__all__ = ["Job"]
