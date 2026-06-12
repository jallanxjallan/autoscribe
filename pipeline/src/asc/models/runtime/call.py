from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import ConfigDict, Field, field_validator

from asc.core.identity import generate_identity
from asc.core.timestamp import timestamp
from asc.models.helpers.plain import plain_non_empty_string
from asc.models.helpers.upload import RedisIdentity, RecordIdentity, RequiredRecordContent
from asc.redis.model_base import RedisModel


class CallRecord(RedisModel):
    """Runtime call/document payload.

    Upload-only ``record_*`` fields are normalized in ``asc.upload.uploader``
    before this model is validated.  The runtime model therefore exposes the
    fields workers should be able to rely on directly: ``content`` for the text
    payload and ``source_slug`` for the external/client slug used in slugmap.
    """

    namespace: ClassVar[str] = "runtime"
    domain: ClassVar[str] = namespace
    kind: ClassVar[str] = "call"

    model_config = ConfigDict(extra="allow")

    type: Literal["call"] = "call"
    identity: RedisIdentity = Field(default_factory=generate_identity)
    source_slug: RecordIdentity
    content: RequiredRecordContent
    created_at: int = Field(default_factory=timestamp)

    @property
    def slug(self) -> str:
        return self.source_slug

    @field_validator("content", mode="before")
    @classmethod
    def validate_content(cls, value: object) -> str:
        return plain_non_empty_string(value, "content")


__all__ = ["CallRecord"]
