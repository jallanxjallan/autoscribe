from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar, Literal

from pydantic import ConfigDict, Field, field_validator

from asc.core.timestamp import timestamp
from asc.models.helpers.plain import plain_non_empty_string, redis_key_segment_text
from asc.redis.model_base import RedisModel


class RuntimeCallRecord(RedisModel):
    """Runtime anchor for the prompt payload attached to one call.

    Plan selection is deliberately not stored here. Enqueue resolves the plan
    slug and writes that mutable orchestration choice to RuntimeCallState.
    """

    model_config = ConfigDict(extra="allow")

    domain: ClassVar[str] = "runtime"
    kind: ClassVar[str] = "call"

    type: Literal["runtime-call"] = "runtime-call"
    identity: str
    record_type: str = "prompt"
    record_identity: str
    record_content: str
    created_at: int = Field(default_factory=timestamp)

    @field_validator("identity", "record_identity", mode="before")
    @classmethod
    def validate_identity(cls, value: object) -> str:
        return redis_key_segment_text(value, "identity")

    @field_validator("record_content", mode="before")
    @classmethod
    def validate_record_content(cls, value: object) -> str:
        return plain_non_empty_string(value, "record_content")

    @classmethod
    def from_raw_record(cls, *, identity: str, raw_record: Mapping[str, Any]) -> "RuntimeCallRecord":
        record = dict(raw_record)
        return cls(
            identity=identity,
            record_type=_required_text(record.get("record_type"), "record_type"),
            record_identity=_required_text(record.get("record_identity"), "record_identity"),
            record_content=_required_text(record.get("record_content"), "record_content"),
            **{
                key: value
                for key, value in record.items()
                if key not in {"record_type", "record_identity", "record_content"}
            },
        )


def _required_text(value: object, field_name: str) -> str:
    return plain_non_empty_string(value, field_name)


__all__ = ["RuntimeCallRecord"]
