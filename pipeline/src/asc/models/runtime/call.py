from __future__ import annotations

from typing import Any, ClassVar, Literal, Mapping

from pydantic import ConfigDict, Field, field_validator, model_validator

from asc.core.timestamp import timestamp
from asc.models.helpers.plain import plain_non_empty_string, redis_key_segment_text, slug_like_text
from asc.redis.model_base import RedisModel


class RuntimeCallRecord(RedisModel):
    """Redis-persisted runtime call anchor for one uploaded prompt/chunk.

    The call owns the uploaded prompt row as raw_json. Executable text begins in
    the runtime content chain at position 1.
    """

    model_config = ConfigDict(extra="ignore")

    domain: ClassVar[str] = "runtime"
    kind: ClassVar[str] = "call"

    type: Literal["runtime-call"] = "runtime-call"
    identity: str
    plan: str
    plan_key: str
    plan_slug: str
    raw_json: dict[str, Any]
    created_at: int = Field(default_factory=timestamp)

    @model_validator(mode="before")
    @classmethod
    def normalize_shape(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        if "raw_json" not in normalized and "raw_record" in normalized:
            normalized["raw_json"] = normalized["raw_record"]
        return normalized

    @field_validator("identity", "plan", mode="before")
    @classmethod
    def validate_identity(cls, value: object) -> str:
        return redis_key_segment_text(value, "identity")

    @field_validator("plan_slug", mode="before")
    @classmethod
    def validate_plan_slug(cls, value: object) -> str:
        return slug_like_text(value)

    @field_validator("plan_key", mode="before")
    @classmethod
    def validate_plan_key(cls, value: object) -> str:
        return plain_non_empty_string(value, "plan_key")

    @field_validator("raw_json", mode="before")
    @classmethod
    def validate_raw_json(cls, value: object) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError("raw_json must be an object")
        return dict(value)

    @classmethod
    def from_raw_record(
        cls,
        *,
        identity: str,
        raw_record: Mapping[str, Any],
        plan: str,
        plan_key: str,
    ) -> "RuntimeCallRecord":
        plan_slug = _plan_slug_from_record(raw_record)
        return cls(
            identity=identity,
            plan=plan,
            plan_key=plan_key,
            plan_slug=plan_slug,
            raw_json=dict(raw_record),
        )

    @property
    def call_identity(self) -> str:
        return self.identity

    @property
    def source_content(self) -> str:
        return _content_from_record(self.raw_json)

    @property
    def prompt_slug(self) -> str | None:
        for key in ("identifier", "slug", "prompt_slug"):
            value = self.raw_json.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None


def _plan_slug_from_record(record: Mapping[str, Any]) -> str:
    value = record.get("plan_slug")
    if value is None:
        raise ValueError("prompt record must include plan_slug")
    return slug_like_text(value)


def _content_from_record(record: Mapping[str, Any]) -> str:
    value = record.get("content")
    if value is None:
        value = record.get("payload_content")
    return plain_non_empty_string(value, "content")


CallRecord = RuntimeCallRecord

__all__ = ["CallRecord", "RuntimeCallRecord"]
