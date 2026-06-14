from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import ConfigDict, Field, field_validator

from asc.core.timestamp import timestamp
from asc.models.helpers.plain import plain_non_empty_string, redis_key_segment_text
from asc.redis.model_base import RedisModel


class RuntimeCursor(RedisModel):
    """Minimal mutable cursor for one runtime call.

    Queue membership determines custody. The fixed response index hash is the
    source of truth for runtime input/output progress:

        runtime:<identity>:responses
          0 = original call key
          1 = response from step 1
          2 = response from step 2
          ...

    Legacy Redis hashes may still contain retired cursor fields such as
    terminal_step, total_steps, fail_code, and fail_message. Ignore unknown
    fields on load so live cursors survive model cleanup.
    """

    model_config = ConfigDict(extra="ignore")

    domain: ClassVar[str] = "runtime"
    kind: ClassVar[str] = "cursor"

    type: Literal["cursor"] = "cursor"

    identity: str
    call_key: str
    plan_key: str

    current_step: int = Field(default=1, ge=1)
    retry_count: int = Field(default=0, ge=0)

    created_at: int = Field(default_factory=timestamp)
    updated_at: int = Field(default_factory=timestamp)

    @property
    def response_index_key(self) -> str:
        return f"runtime:{self.identity}:responses"

    # Legacy compatibility: callers should move to the response index helpers.
    @property
    def is_terminal_step(self) -> bool:
        from asc.runtime.response_index import response_index_complete

        return response_index_complete(self.response_index_key)

    @property
    def input_key(self) -> str:
        from asc.runtime.response_index import response_input_key

        return response_input_key(self.response_index_key, self.current_step)

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
