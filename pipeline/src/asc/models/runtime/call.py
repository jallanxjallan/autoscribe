from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar, Literal

from pydantic import ConfigDict, Field, field_validator

from asc.core.identity import generate_identity
from asc.core.timestamp import timestamp
from asc.models.helpers.plain import plain_non_empty_string
from asc.models.helpers.upload import (
    ExternalUploadRecordMixin,
    RecordIdentity,
    RedisIdentity,
    RequiredRecordContent,
    record_type_text,
)
from asc.redis.model_base import RedisModel


class CallRecord(ExternalUploadRecordMixin, RedisModel):
    """Canonical uploaded call/document payload.

    A call is now the single upload-facing document record.  Public upload
    records provide record_* fields; the runtime ``identity`` remains the Redis
    key identity.  Unknown source fields are preserved as Redis baggage for
    downstream export consumers.

    Plan selection is deliberately not stored here. Enqueue resolves the plan
    slug and writes that mutable orchestration choice to runtime call state.
    """

    namespace: ClassVar[str] = "runtime"
    domain: ClassVar[str] = namespace
    kind: ClassVar[str] = "call"

    model_config = ConfigDict(extra="allow")

    type: Literal["call"] = "call"
    record_type: Literal["call"] = "call"
    identity: RedisIdentity = Field(default_factory=generate_identity)
    record_identity: RecordIdentity
    record_content: RequiredRecordContent
    created_at: int = Field(default_factory=timestamp)

    @property
    def slug(self) -> str:
        return self.record_identity

    @property
    def content(self) -> str:
        """Compatibility accessor for older callers that read call.content."""
        return self.record_content

    @field_validator("record_type", mode="before")
    @classmethod
    def validate_record_type(cls, value: object) -> str:
        return record_type_text(value, expected=cls.kind)

    @field_validator("record_content", mode="before")
    @classmethod
    def validate_record_content(cls, value: object) -> str:
        return plain_non_empty_string(value, "record_content")

    @classmethod
    def from_raw_record(cls, *, identity: str | None = None, raw_record: Mapping[str, Any]) -> "CallRecord":
        """Build a CallRecord from public upload NDJSON.

        The canonical public shape is record_type / record_identity /
        record_content.  Legacy ``type`` and ``content`` inputs are accepted only
        to make the transition fail-loud-but-readable at the boundary.
        """
        record = dict(raw_record)

        record_type = record.pop("record_type", record.pop("type", cls.kind))
        record_identity = record.pop("record_identity", record.pop("identity", None))
        record_content = record.pop("record_content", record.pop("content", None))

        data: dict[str, Any] = {
            "record_type": record_type,
            "record_identity": record_identity,
            "record_content": record_content,
            **record,
        }
        if identity is not None:
            data["identity"] = identity

        return cls(**data)


__all__ = ["CallRecord"]
