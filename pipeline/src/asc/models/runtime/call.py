from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar, Literal

from pydantic import ConfigDict, Field, field_validator

from asc.core.timestamp import timestamp
from asc.models.helpers.plain import plain_non_empty_string, redis_key_segment_text
from asc.redis.model_base import RedisModel


class RuntimeCallRecord(RedisModel):
    """Redis-persisted runtime call anchor for one uploaded record."""

    model_config = ConfigDict(extra="allow")

    domain: ClassVar[str] = "runtime"
    kind: ClassVar[str] = "call"

    type: Literal["runtime-call"] = "runtime-call"
    identity: str
    plan: str
    plan_key: str
    plan_slug: str | None = None
    record_type: str = "prompt"
    record_identity: str
    record_content: str
    created_at: int = Field(default_factory=timestamp)

    @field_validator("identity", "plan", mode="before")
    @classmethod
    def validate_identity(cls, value: object) -> str:
        return redis_key_segment_text(value, "identity")

    @field_validator("plan_key", mode="before")
    @classmethod
    def validate_plan_key(cls, value: object) -> str:
        return plain_non_empty_string(value, "plan_key")

    @field_validator("record_identity", mode="before")
    @classmethod
    def validate_record_identity(cls, value: object) -> str:
        return redis_key_segment_text(value, "record_identity")

    @field_validator("record_content", mode="before")
    @classmethod
    def validate_record_content(cls, value: object) -> str:
        return plain_non_empty_string(value, "record_content")

    @classmethod
    def from_raw_record(
        cls,
        *,
        identity: str,
        raw_record: Mapping[str, Any],
        plan: str,
        plan_key: str,
    ) -> "RuntimeCallRecord":
        record = dict(raw_record)
        return cls(
            identity=identity,
            plan=plan,
            plan_key=plan_key,
            plan_slug=_optional_text(record.get("plan_slug")),
            record_type=_required_text(record.get("record_type"), "record_type"),
            record_identity=_required_text(record.get("record_identity"), "record_identity"),
            record_content=_required_text(record.get("record_content"), "record_content"),
            **{
                key: value
                for key, value in record.items()
                if key not in {"record_type", "record_identity", "record_content", "plan_slug"}
            },
        )

    @property
    def call_identity(self) -> str:
        return self.identity

    @property
    def source_content(self) -> str:
        return self.record_content

    @property
    def prompt_slug(self) -> str:
        return self.record_identity

    @property
    def raw_json(self) -> dict[str, Any]:
        return {
            "record_type": self.record_type,
            "record_identity": self.record_identity,
            "record_content": self.record_content,
            **dict(self.model_extra or {}),
        }


def _required_text(value: object, field_name: str) -> str:
    return plain_non_empty_string(value, field_name)


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("optional text field must be a plain string")
    value = value.strip()
    return value or None


CallRecord = RuntimeCallRecord

__all__ = ["CallRecord", "RuntimeCallRecord"]
