"""Persisted orchestration jobs for active calls."""

from __future__ import annotations

from typing import ClassVar, Literal, Self

from pydantic import ConfigDict, Field, field_serializer, field_validator, model_validator

from asc.core.timestamp import timestamp
from asc.models.helpers.plain import redis_key_segment_text
from asc.redis.model_base import RedisModel


class Job(RedisModel):
    """One call registered for orchestration.

    The job shares the call identity, so its Redis key is deterministic:

        job:<call_identity>:record

    Runtime records are addressed separately as
    ``runtime:<call_identity>:<ordinal>``. The active-jobs sorted set contains
    this job key and is the only scheduling index.

    The mutable ``*_hint`` fields are lookup accelerators only. They may be
    stale after a crash and must never be treated as orchestration state. The
    authoritative history is the set of task, result, and failure artifacts
    for the call identity. The orchestrator starts from these hints, verifies
    the artifacts, derives the real state, and then refreshes the hints.
    """

    model_config = ConfigDict(extra="forbid")

    kind: ClassVar[str] = "job"
    component: ClassVar[Literal["record"]] = "record"

    identity: str
    plan_identity: str
    total_steps: int
    result_ordinal_hint: int = 0
    task_ordinal_hint: int = 0
    task_created_at_hint: int = 0
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

    @field_validator(
        "result_ordinal_hint",
        "task_ordinal_hint",
        "task_created_at_hint",
        mode="before",
    )
    @classmethod
    def validate_nonnegative_hint(cls, value: object) -> int:
        hint = int(value)
        if hint < 0:
            raise ValueError("job hints must not be negative")
        return hint

    @model_validator(mode="after")
    def validate_ordinal_hints(self) -> Self:
        if self.result_ordinal_hint > self.total_steps:
            raise ValueError("job result_ordinal_hint exceeds total_steps")
        if self.task_ordinal_hint > self.total_steps:
            raise ValueError("job task_ordinal_hint exceeds total_steps")
        return self

    @field_serializer(
        "created_at",
        "total_steps",
        "result_ordinal_hint",
        "task_ordinal_hint",
        "task_created_at_hint",
    )
    def serialize_int(self, value: int) -> str:
        return str(value)


__all__ = ["Job"]
