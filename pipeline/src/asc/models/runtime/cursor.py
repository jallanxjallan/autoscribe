from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import ConfigDict, Field, field_validator

from asc.core.timestamp import timestamp
from asc.models.helpers.plain import plain_non_empty_string, redis_key_segment_text
from asc.redis.model_base import RedisModel


class RuntimeCursor(RedisModel):
    """Immutable runtime cursor for one call.

    Queue membership determines custody.
    The response index determines progress.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    domain: ClassVar[str] = "runtime"
    kind: ClassVar[str] = "cursor"

    type: Literal["cursor"] = "cursor"

    identity: str
    call_key: str
    plan_key: str

    created_at: int = Field(default_factory=timestamp)

    @property
    def response_index_key(self) -> str:
        return f"runtime:{self.identity}:responses"

    @property
    def completed_step_count(self) -> int:
        from asc.runtime.response_index import response_completed_step_count

        return response_completed_step_count(self.response_index_key)

    @property
    def current_step(self) -> int:
        return self.completed_step_count + 1

    @property
    def input_key(self) -> str:
        from asc.runtime.response_index import response_input_key

        return response_input_key(self.response_index_key, self.current_step)

    @property
    def output_key(self) -> str:
        return f"runtime:{self.identity}:response.{self.current_step}"

    @property
    def is_complete(self) -> bool:
        from asc.runtime.response_index import response_index_complete

        return response_index_complete(self.response_index_key)

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