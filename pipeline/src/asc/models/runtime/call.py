from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar, Literal
import json

from pydantic import ConfigDict, Field, field_serializer, field_validator, model_validator

from asc.core.identity import generate_identity
from asc.core.timestamp import timestamp
from asc.models.helpers.plain import plain_non_empty_string
from asc.models.helpers.upload import RedisIdentity, RecordIdentity, RequiredRecordContent
from asc.redis.model_base import RedisModel


class CallRecord(RedisModel):
    """Runtime call/source payload."""

    namespace: ClassVar[str] = "runtime"
    domain: ClassVar[str] = namespace
    kind: ClassVar[str] = "call"

    model_config = ConfigDict(extra="allow")

    type: Literal["call"] = "call"
    identity: RedisIdentity = Field(default_factory=generate_identity)
    source_identity: RecordIdentity
    content: RequiredRecordContent
    source_json: str = "{}"
    created_at: int = Field(default_factory=timestamp)

    @model_validator(mode="before")
    @classmethod
    def normalize_upload_envelope(cls, value: object) -> object:
        if not isinstance(value, Mapping):
            return value

        data: dict[str, Any] = dict(value)

        if "record_identity" in data and "source_identity" not in data:
            data["source_identity"] = data["record_identity"]

        if "record_content" in data and "content" not in data:
            data["content"] = data["record_content"]

        raw_type = data.get("type")
        if raw_type != "call":
            data["source_record_type"] = raw_type
            data["type"] = "call"

        data.pop("record_type", None)
        data.pop("record_content", None)

        # Uploads are immutable. Never reuse a client-emitted Redis identity.
        data.pop("identity", None)

        if "source" in data and "source_json" not in data:
            data["source_json"] = json.dumps(
                data.pop("source"),
                ensure_ascii=False,
                separators=(",", ":"),
            )

        return data

    @field_validator("content", mode="before")
    @classmethod
    def validate_content(cls, value: object) -> str:
        return plain_non_empty_string(value, "content")

    @field_serializer("source_json", when_used="json")
    def serialize_source_json(self, value: str) -> str:
        return value


__all__ = ["CallRecord"]
