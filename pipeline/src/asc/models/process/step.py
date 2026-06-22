"""Short-lived executable step records."""

from __future__ import annotations

import json
from typing import Any, ClassVar

from pydantic import ConfigDict, Field, field_serializer, field_validator

from asc.core.identity import generate_identity
from asc.core.timestamp import timestamp
from asc.models.helpers.plain import redis_key_segment_text
from asc.redis.message_base import RedisMessage


class Step(RedisMessage):
    """Materialized worker instruction for one call step.

    A Step is the compiled runtime form of one plan step.  Workers receive the
    Step key and the Call key; they do not reload or unpack the Plan.
    Executor-specific fields are intentionally allowed as extras.
    """

    model_config = ConfigDict(extra="allow")

    kind: ClassVar[str] = "step"

    identity: str = Field(default_factory=generate_identity)

    call_key: str
    cursor_key: str
    step_number: int

    executor: str
    action: str

    instructions_json: str = "[]"
    args_json: str = "{}"

    created_at: int = Field(default_factory=timestamp)

    @field_validator("identity", mode="before")
    @classmethod
    def validate_identity(cls, value: object) -> str:
        return redis_key_segment_text(value, "identity")

    @field_validator("call_key", "cursor_key", mode="before")
    @classmethod
    def validate_full_key(cls, value: object) -> str:
        text = "" if value is None else str(value).strip()
        if not text:
            raise ValueError("runtime key fields must be non-empty")
        if ":" not in text:
            raise ValueError(f"expected full Redis key, got {text!r}")
        return text

    @field_validator("executor", "action", mode="before")
    @classmethod
    def validate_required_text(cls, value: object) -> str:
        text = "" if value is None else str(value).strip()
        if not text:
            raise ValueError("executor/action must be non-empty")
        return text

    @field_validator("step_number", mode="before")
    @classmethod
    def validate_step_number(cls, value: object) -> int:
        number = int(value)
        if number < 1:
            raise ValueError("step_number must be >= 1")
        return number

    @field_validator("instructions_json", "args_json", mode="before")
    @classmethod
    def validate_json_text(cls, value: object) -> str:
        if value is None or value == "":
            value = []
        if isinstance(value, str):
            json.loads(value)
            return value
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)

    @field_serializer("created_at", "step_number")
    def serialize_ints(self, value: int) -> str:
        return str(value)


__all__ = ["Step"]
