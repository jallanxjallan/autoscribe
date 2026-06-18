from __future__ import annotations

from typing import ClassVar

from pydantic import ConfigDict, Field, field_serializer, field_validator

from asc.core.identity import generate_identity
from asc.core.timestamp import timestamp
from asc.models.helpers.plain import plain_non_empty_string
from asc.models.helpers.upload import RedisIdentity, RecordIdentity, RequiredRecordContent
from asc.redis.model_base import RedisModel


class Call(RedisModel):
    """Immutable source payload for one process call."""

    model_config = ConfigDict(extra="forbid")

    kind: ClassVar[str] = "call"
    suffix: ClassVar[str] = "record"

    identity: RedisIdentity = Field(default_factory=generate_identity)
    source_identity: RecordIdentity
    content: RequiredRecordContent
    source_json: str = "{}"
    created_at: int = Field(default_factory=timestamp)

    @field_validator("content", mode="before")
    @classmethod
    def validate_content(cls, value: object) -> str:
        return plain_non_empty_string(value, "content")

    @field_serializer("source_json", when_used="json")
    def serialize_source_json(self, value: str) -> str:
        return value


__all__ = ["Call"]
