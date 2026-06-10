from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import ConfigDict, Field, field_validator, model_validator

from asc.core.identity import generate_identity
from asc.models.helpers.upload import (
    ExternalUploadRecordMixin,
    OptionalRecordContent,
    RecordIdentity,
    RedisIdentity,
    record_type_text,
)
from asc.redis.model_base import RedisModel


class UploadedAssetRecord(ExternalUploadRecordMixin, RedisModel):
    """Stub for separately uploaded assets.

    Assets such as images and reference files should be uploaded independently.
    Matching prompt/control records should refer to them by hard asset identity
    in their first-class assets list or source baggage.
    """

    namespace: ClassVar[str] = "uploaded"
    domain: ClassVar[str] = namespace
    kind: ClassVar[str] = "asset"

    model_config = ConfigDict(extra="allow")

    record_type: Literal["asset"]
    identity: RedisIdentity = Field(default_factory=generate_identity)
    slug: RecordIdentity
    record_identity: RecordIdentity
    record_content: OptionalRecordContent = ""

    @model_validator(mode="before")
    @classmethod
    def normalize_upload_shape(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        normalized.pop("identity", None)
        if "record_type" not in normalized and "type" in normalized:
            normalized["record_type"] = normalized.pop("type")
        if "record_identity" in normalized:
            normalized["slug"] = normalized["record_identity"]
        elif "slug" in normalized:
            normalized["record_identity"] = normalized["slug"]
        return normalized

    @field_validator("record_type", mode="before")
    @classmethod
    def validate_record_type(cls, value: object) -> str:
        return record_type_text(value, expected=cls.kind)


__all__ = ["UploadedAssetRecord"]
