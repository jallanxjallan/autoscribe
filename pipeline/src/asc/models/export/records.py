from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from asc.models.helpers.plain import plain_non_empty_string, redis_key_segment_text, slug_like_text


class _ExportBase(BaseModel):
    model_config = ConfigDict(extra="ignore")

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> Self:
        """Validate a SQL row or row-like mapping as an export stream record."""
        return cls.model_validate(dict(row))


class PendingExportRecord(_ExportBase):
    """Typed row emitted by pending export listing."""

    type: Literal["pending-export"]
    prompt_slug: str
    call_identity: str
    result_identity: str
    plan_slug: str | None = None
    created_at: str | int | None = None
    raw_record: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def normalize_row_shape(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value

        normalized = dict(value)
        normalized.setdefault("type", "pending-export")
        return normalized

    @field_validator("prompt_slug", mode="before")
    @classmethod
    def validate_prompt_slug(cls, value: object) -> str:
        return slug_like_text(value, "prompt_slug")

    @field_validator("plan_slug", mode="before")
    @classmethod
    def validate_plan_slug(cls, value: object) -> str | None:
        if value is None:
            return None
        return slug_like_text(value, "plan_slug")

    @field_validator("call_identity", "result_identity", mode="before")
    @classmethod
    def validate_identity(cls, value: object) -> str:
        return redis_key_segment_text(value, "identity")


class ExtractedResultRecord(_ExportBase):
    """Typed row emitted by export result extraction."""

    type: Literal["extracted-result"]
    prompt_slug: str
    call_identity: str
    result_identity: str
    content: str
    plan_slug: str | None = None
    raw_record: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def normalize_row_shape(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value

        normalized = dict(value)
        normalized.setdefault("type", "extracted-result")
        return normalized

    @field_validator("prompt_slug", mode="before")
    @classmethod
    def validate_prompt_slug(cls, value: object) -> str:
        return slug_like_text(value, "prompt_slug")

    @field_validator("plan_slug", mode="before")
    @classmethod
    def validate_plan_slug(cls, value: object) -> str | None:
        if value is None:
            return None
        return slug_like_text(value, "plan_slug")

    @field_validator("call_identity", "result_identity", mode="before")
    @classmethod
    def validate_identity(cls, value: object) -> str:
        return redis_key_segment_text(value, "identity")

    @field_validator("content", mode="before")
    @classmethod
    def validate_content(cls, value: object) -> str:
        return plain_non_empty_string(value, "content")


class ExportUpdateRecord(_ExportBase):
    """Typed record consumed when marking an exported result complete."""

    type: Literal["export-update"]
    result_identity: str

    @model_validator(mode="before")
    @classmethod
    def normalize_row_shape(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value

        normalized = dict(value)
        normalized.setdefault("type", "export-update")
        return normalized

    @field_validator("result_identity", mode="before")
    @classmethod
    def validate_result_identity(cls, value: object) -> str:
        return redis_key_segment_text(value, "result_identity")


__all__ = [
    "ExportUpdateRecord",
    "ExtractedResultRecord",
    "PendingExportRecord",
]
