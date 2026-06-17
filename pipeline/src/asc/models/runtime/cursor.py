from __future__ import annotations

from typing import ClassVar

from pydantic import ConfigDict, Field, field_validator

from asc.core.timestamp import timestamp
from asc.models.helpers.plain import plain_non_empty_string, redis_key_segment_text
from asc.redis.model_base import RedisModel


class Cursor(RedisModel):
    """Runtime baton for one call.

    Progress is derived from the current job and ledger artifacts.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: ClassVar[str] = "cursor"
    suffix: ClassVar[str] = "index"


    identity: str
    call_key: str
    plan_key: str

    created_at: int = Field(default_factory=timestamp)

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

    


__all__ = ["Cursor"]