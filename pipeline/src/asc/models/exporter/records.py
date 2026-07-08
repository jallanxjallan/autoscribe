from collections.abc import Mapping
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from asc.models.helpers.plain import plain_non_empty_string, redis_key_segment_text, slug_like_text


class _ExportBase(BaseModel):
    model_config = ConfigDict(extra="allow")

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> Self:
        return cls.model_validate(dict(row))


def _copy_source_compat_fields(data: dict[str, Any]) -> None:
    source_identity = data.get("source_identity") or data.get("record_identity") or data.get("prompt_slug")
    if source_identity is not None:
        data.setdefault("source_identity", source_identity)
        data.setdefault("record_identity", source_identity)
        data.setdefault("prompt_slug", source_identity)

    result_key = data.get("result_key") or data.get("result_identity")
    if result_key is not None:
        data.setdefault("result_key", result_key)
        data.setdefault("result_identity", result_key)


class PendingExportRecord(_ExportBase):
    type: Literal["pending-export"] = "pending-export"
    source_identity: str
    call_identity: str
    final_step: int
    result_key: str
    record_identity: str | None = None
    prompt_slug: str | None = None
    result_identity: str | None = None
    created_at: str | int | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_row_shape(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        data.setdefault("type", "pending-export")
        _copy_source_compat_fields(data)
        return data

    @field_validator("source_identity", "record_identity", "prompt_slug", mode="before")
    @classmethod
    def validate_source_identity(cls, value: object) -> str | None:
        if value is None:
            return None
        return slug_like_text(value, "source_identity")

    @field_validator("call_identity", mode="before")
    @classmethod
    def validate_call_identity(cls, value: object) -> str:
        return redis_key_segment_text(value, "call_identity")

    @field_validator("result_key", "result_identity", mode="before")
    @classmethod
    def validate_result_key(cls, value: object) -> str | None:
        if value is None:
            return None
        return plain_non_empty_string(value, "result_key")


class ExtractedResultRecord(_ExportBase):
    type: Literal["extracted-result"] = "extracted-result"
    source_identity: str
    call_identity: str
    final_step: int
    result_key: str
    content: str
    record_identity: str | None = None
    prompt_slug: str | None = None
    result_identity: str | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_row_shape(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        data.setdefault("type", "extracted-result")
        _copy_source_compat_fields(data)
        return data

    @field_validator("source_identity", "record_identity", "prompt_slug", mode="before")
    @classmethod
    def validate_source_identity(cls, value: object) -> str | None:
        if value is None:
            return None
        return slug_like_text(value, "source_identity")

    @field_validator("call_identity", mode="before")
    @classmethod
    def validate_call_identity(cls, value: object) -> str:
        return redis_key_segment_text(value, "call_identity")

    @field_validator("result_key", "result_identity", mode="before")
    @classmethod
    def validate_result_key(cls, value: object) -> str | None:
        if value is None:
            return None
        return plain_non_empty_string(value, "result_key")

    @field_validator("content", mode="before")
    @classmethod
    def validate_content(cls, value: object) -> str:
        return plain_non_empty_string(value, "content")


class ExportUpdateRecord(_ExportBase):
    type: Literal["export-update"] = "export-update"
    result_identity: str = Field(description="Full result key or bare call identity.")

    @model_validator(mode="before")
    @classmethod
    def normalize_row_shape(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        data.setdefault("type", "export-update")
        return data

    @field_validator("result_identity", mode="before")
    @classmethod
    def validate_result_identity(cls, value: object) -> str:
        return plain_non_empty_string(value, "result_identity")


__all__ = ["ExportUpdateRecord", "ExtractedResultRecord", "PendingExportRecord"]
