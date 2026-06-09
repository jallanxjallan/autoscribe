from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import ConfigDict, Field, field_validator, model_validator

from asc.core.identity import generate_identity
from asc.models.helpers.upload import RecordIdentity, RedisIdentity, RequiredRecordContent, asset_list
from asc.redis.model_base import RedisModel


class InstructionRecord(RedisModel):
    """Uploaded reusable instruction control asset.

    Canonical upload contract: record_type, record_identity, record_content.
    All non-contract client/source fields live in model_extra.
    """

    namespace: ClassVar[str] = "control"
    domain: ClassVar[str] = namespace
    kind: ClassVar[str] = "instruction"

    model_config = ConfigDict(extra="allow")

    type: Literal["instruction"] = "instruction"
    record_type: Literal["instruction"] = "instruction"
    identity: RedisIdentity = Field(default_factory=generate_identity)
    slug: RecordIdentity
    record_identity: RecordIdentity
    record_content: RequiredRecordContent
    assets: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_upload_shape(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        if "record_identity" in normalized:
            normalized["slug"] = normalized["record_identity"]
        elif "slug" in normalized:
            normalized["record_identity"] = normalized["slug"]
        return normalized

    @field_validator("assets", mode="before")
    @classmethod
    def validate_assets(cls, value: object) -> list[str]:
        return asset_list(value)


__all__ = ["InstructionRecord"]
