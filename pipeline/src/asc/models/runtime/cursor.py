from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import ConfigDict, Field, field_validator

from asc.core.timestamp import timestamp
from asc.models.helpers.plain import plain_non_empty_string, redis_key_segment_text
from asc.redis.model_base import RedisModel


class RuntimeCursor(RedisModel):
    """Mutable orchestration cursor for one runtime call.

    Worker-facing fields are full Redis keys only:

        document_key
            Resolved uploaded document key captured at enqueue time.

        input_key
            The content-bearing key the worker should read for this step.
            For step 1 this is document_key. For later steps this is the
            previous RuntimeContentRecord key.

        step_key
            The materialized RuntimeStepRecord key for this step.

        response_key
            The RuntimeContentRecord key the worker should write.
    """

    model_config = ConfigDict(extra="forbid")

    domain: ClassVar[str] = "runtime"
    kind: ClassVar[str] = "call"

    type: Literal["call"] = "call"
    identity: str

    document_key: str
    plan_key: str
    input_key: str
    step_key: str
    response_key: str

    status: Literal["pending", "running", "retry", "failed", "complete"] = "pending"
    current_step: int = Field(default=1, ge=1)
    last_step_completed: int = Field(default=0, ge=0)
    retry_count: int = Field(default=0, ge=0)
    fail_code: str | None = None
    fail_message: str | None = None
    created_at: int = Field(default_factory=timestamp)
    updated_at: int = Field(default_factory=timestamp)

    @field_validator("identity", mode="before")
    @classmethod
    def validate_identity(cls, value: object) -> str:
        return redis_key_segment_text(value, "identity")

    @field_validator(
        "document_key",
        "plan_key",
        "input_key",
        "step_key",
        "response_key",
        mode="before",
    )
    @classmethod
    def validate_full_key(cls, value: object) -> str:
        text = plain_non_empty_string(value, "runtime key")
        if ":" not in text:
            raise ValueError(f"call key must be a full Redis key, got {text!r}")
        return text


__all__ = ["Call"]