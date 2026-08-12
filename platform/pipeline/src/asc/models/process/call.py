"""Persisted uploaded call records."""

import json
from typing import ClassVar

from pydantic import ConfigDict, Field, field_validator

from asc.core.identity import generate_identity
from asc.core.timestamp import timestamp
from asc.redis.model_base import RedisModel


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    text = value.strip()
    if "\x00" in text:
        raise ValueError(f"{field_name} must not contain NUL bytes")
    return text


def _json_object_text(value: object, field_name: str) -> str:
    if value in (None, ""):
        return "{}"
    if isinstance(value, str):
        parsed = json.loads(value)
    else:
        parsed = value
    if not isinstance(parsed, dict):
        raise ValueError(f"{field_name} must be an object")
    return json.dumps(parsed, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class CallRecord(RedisModel):
    """Uploaded call content, independent of any processing plan."""

    model_config = ConfigDict(extra="forbid")

    kind: ClassVar[str] = "call"
    component: ClassVar[str] = "record"

    identity: str = Field(default_factory=generate_identity)
    source_identity: str
    content: str
    created_at: int = Field(default_factory=timestamp)
    extra_json: str = "{}"

    @field_validator("identity", "source_identity", mode="before")
    @classmethod
    def validate_identity_text(cls, value: object, info):
        return _required_text(value, info.field_name)

    @field_validator("content", mode="before")
    @classmethod
    def validate_content(cls, value: object) -> str:
        return _required_text(value, "content")

    @field_validator("extra_json", mode="before")
    @classmethod
    def validate_extra_json(cls, value: object) -> str:
        return _json_object_text(value, "extra_json")


__all__ = ["CallRecord"]
