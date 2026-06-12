from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import ConfigDict, Field, field_validator

from asc.core.timestamp import timestamp
from asc.models.helpers.plain import plain_non_empty_string, redis_key_segment_text
from asc.redis.model_base import RedisModel


class RuntimeCursor(RedisModel):
    """Mutable orchestration cursor for one runtime call.

    The cursor exists only while a call is actively moving through the
    pipeline. It stores the minimum durable state required to resume
    orchestration.

    All worker-facing keys are derived from:

        identity
        current_step

    and therefore are exposed as computed properties rather than persisted
    fields.
    """

    model_config = ConfigDict(extra="forbid")

    domain: ClassVar[str] = "runtime"
    kind: ClassVar[str] = "cursor"

    type: Literal["cursor"] = "cursor"

    identity: str

    call_key: str
    plan_key: str

    status: Literal[
        "pending",
        "running",
        "failed",
        "complete",
    ] = "pending"

    current_step: int = Field(default=1, ge=1)
    last_step_completed: int = Field(default=0, ge=0)

    retry_count: int = Field(default=0, ge=0)

    fail_code: str | None = None
    fail_message: str | None = None

    created_at: int = Field(default_factory=timestamp)
    updated_at: int = Field(default_factory=timestamp)

    @property
    def step_key(self) -> str:
        return f"runtime:{self.identity}:step.{self.current_step}"

    @property
    def input_key(self) -> str:
        if self.current_step == 1:
            return self.call_key
        return f"runtime:{self.identity}:response.{self.current_step - 1}"

    @property
    def output_key(self) -> str:
        return f"runtime:{self.identity}:response.{self.current_step}"

    @field_validator("identity", mode="before")
    @classmethod
    def validate_identity(cls, value: object) -> str:
        return redis_key_segment_text(value, "identity")

    @field_validator("call_key", "plan_key", mode="before")
    @classmethod
    def validate_full_key(cls, value: object) -> str:
        text = plain_non_empty_string(value, "runtime key")
        if ":" not in text:
            raise ValueError(f"expected full Redis key, got {text!r}")
        return text


__all__ = ["RuntimeCursor"]