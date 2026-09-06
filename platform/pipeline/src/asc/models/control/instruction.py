"""Persisted reusable instruction records."""

import json
import re
from typing import ClassVar

from pydantic import ConfigDict, Field, field_validator, model_validator

from asc.core.identity import generate_identity
from asc.models.control.plan import instruction_scope
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


class Instruction(RedisModel):
    """Reusable content materialized from a pinned Git instruction blob."""

    kind: ClassVar[str] = "instruction"
    component: ClassVar[str] = "record"

    model_config = ConfigDict(extra="forbid")

    identity: str = Field(default_factory=generate_identity)
    control_identity: str = ""
    source_fingerprint: str = ""
    title: str
    content: str
    content_sha256: str = ""
    extra_json: str = "{}"

    @model_validator(mode="after")
    def validate_source_version(self):
        if self.control_identity or self.source_fingerprint:
            instruction_scope(self.control_identity, published=True)
            if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", self.source_fingerprint):
                raise ValueError("source_fingerprint must be a Git blob object ID")
        return self

    @field_validator("identity", "title", mode="before")
    @classmethod
    def validate_identity_text(cls, value: object, info):
        return _required_text(value, info.field_name)

    @field_validator("content", mode="before")
    @classmethod
    def validate_content(cls, value: object) -> str:
        _required_text(value, "content")
        return value

    @field_validator("content_sha256", mode="before")
    @classmethod
    def validate_content_sha256(cls, value: object) -> str:
        text = str(value or "").strip().lower()
        if not text:
            return ""
        if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
            raise ValueError("content_sha256 must be a lowercase SHA-256 hex digest")
        return text

    @field_validator("extra_json", mode="before")
    @classmethod
    def validate_extra_json(cls, value: object) -> str:
        return _json_object_text(value, "extra_json")


__all__ = ["Instruction"]
