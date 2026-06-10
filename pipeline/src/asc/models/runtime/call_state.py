from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import ConfigDict, Field, field_validator

from asc.core.timestamp import timestamp
from asc.models.helpers.plain import redis_key_segment_text
from asc.redis.model_base import RedisModel


class RuntimeCallState(RedisModel):
    """Mutable orchestration cursor for one runtime call."""

    model_config = ConfigDict(extra="allow")

    domain: ClassVar[str] = "runtime"
    kind: ClassVar[str] = "state"

    type: Literal["runtime-state"] = "runtime-state"
    identity: str
    plan: str

    status: Literal["pending", "running", "retry", "failed", "complete"] = "pending"
    last_step_completed: int = 0
    retry_count: int = 0
    fail_code: str | None = None
    fail_message: str | None = None
    created_at: int = Field(default_factory=timestamp)
    updated_at: int = Field(default_factory=timestamp)

    @field_validator("identity", "plan", mode="before")
    @classmethod
    def validate_identity(cls, value: object) -> str:
        return redis_key_segment_text(value, "identity")

    @property
    def call_identity(self) -> str:
        return self.identity

    @property
    def plan_identity(self) -> str:
        return self.plan


CallState = RuntimeCallState

__all__ = ["CallState", "RuntimeCallState"]
