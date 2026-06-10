from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import ConfigDict, Field, field_validator

from asc.core.identity import generate_identity
from asc.models.helpers.upload import (
    ExternalUploadRecordMixin,
    RecordIdentity,
    RedisIdentity,
    RequiredRecordContent,
    record_type_text,
)
from asc.redis.model_base import RedisModel


class UploadedRecord(ExternalUploadRecordMixin, RedisModel):
    """Canonical uploaded prompt record.

    Public upload records must provide record_* fields. Unknown source fields
    are carried as Redis baggage for export consumers.
    """

    namespace: ClassVar[str] = "uploaded"
    domain: ClassVar[str] = namespace
    kind: ClassVar[str] = "prompt"

    model_config = ConfigDict(extra="allow")

    record_type: Literal["prompt"]
    identity: RedisIdentity = Field(default_factory=generate_identity)
    record_identity: RecordIdentity
    record_content: RequiredRecordContent

    @property
    def slug(self) -> str:
        return self.record_identity

    @field_validator("record_type", mode="before")
    @classmethod
    def validate_record_type(cls, value: object) -> str:
        return record_type_text(value, expected=cls.kind)


__all__ = ["UploadedRecord"]