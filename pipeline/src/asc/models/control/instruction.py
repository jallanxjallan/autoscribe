from __future__ import annotations

from typing import Any, ClassVar, Literal

from asc.core.identity import generate_identity

from pydantic import ConfigDict, Field, field_validator, model_validator

from asc.models.helpers.plain import (
    plain_non_empty_string,
    redis_key_segment_text,
    slug_like_text,
)
from asc.models.helpers.upload import asset_list, optional_text, plain_object, required_text
from asc.redis.model_base import RedisModel
from asc.streams.upload_normalizer import prepare_upload_record



class InstructionRecord(RedisModel):
    """
    Uploaded reusable instruction control asset.

    Upload records must arrive as canonical JSON objects with top-level
    type="instruction" and identifier="ins.some-slug.x1y2z3". Intake may derive
    slug from identifier, but it does not rescue nested or aliased model fields.

    Instruction content is part of the instruction contract and must be present
    as a non-empty top-level content field.
    """

    namespace: ClassVar[str] = "control"
    domain: ClassVar[str] = namespace
    kind: ClassVar[str] = "instruction"

    model_config = ConfigDict(extra="ignore")

    type: Literal["instruction"]
    identity: str = Field(default_factory=generate_identity)
    identifier: str
    identifier_kind: Literal["slug"]
    slug: str
    content: str
    label: str | None = None
    description: str = ""
    assets: list[str] = Field(default_factory=list)
    source: dict[str, Any] = Field(default_factory=dict)
    raw_record: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def prepare_record(cls, value: object) -> object:
        return prepare_upload_record(
            value,
            allowed_types={"instruction"},
            identifier_kinds={"slug"},
        )

    @field_validator("identity", mode="before")
    @classmethod
    def validate_identity(cls, value: object) -> str:
        return redis_key_segment_text(value, "identity")

    @field_validator("identifier", mode="before")
    @classmethod
    def validate_identifier(cls, value: object) -> str:
        return plain_non_empty_string(value, "identifier").strip()

    @field_validator("slug", mode="before")
    @classmethod
    def validate_slug(cls, value: object) -> str:
        return slug_like_text(value)

    @field_validator("label", mode="before")
    @classmethod
    def validate_label(cls, value: object) -> str | None:
        if value is None:
            return None
        return plain_non_empty_string(value, "label").strip()

    @field_validator("description", mode="before")
    @classmethod
    def validate_description(cls, value: object) -> str:
        return optional_text(value, "description")

    @field_validator("content", mode="before")
    @classmethod
    def validate_content(cls, value: object) -> str:
        return required_text(value, "content")

    @field_validator("assets", mode="before")
    @classmethod
    def validate_assets(cls, value: object) -> list[str]:
        return asset_list(value)

    @field_validator("source", "raw_record", mode="before")
    @classmethod
    def validate_plain_object(cls, value: object) -> dict[str, Any]:
        return plain_object(value, "object")


__all__ = ["InstructionRecord"]
