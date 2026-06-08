from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from asc.models.helpers.plain import plain_non_empty_string, slug_like_text


class UploadedRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    record_type: Literal["prompt"]
    record_identity: str | None = None
    plan_slug: str
    content: str
    raw_record: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def normalize_upload_shape(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value

        normalized = dict(value)

        normalized["record_type"] = (
            normalized.get("record_type")
            or normalized.get("type")
        )

        normalized["record_identity"] = (
            normalized.get("record_identity")
            or normalized.get("identifier")
            or normalized.get("slug")
            or normalized.get("prompt_slug")
        )

        if "plan_slug" not in normalized:
            normalized["plan_slug"] = normalized.get("payload_frontmatter_plan_slug")
        if "content" not in normalized:
            normalized["content"] = normalized.get("payload_content")

        normalized.setdefault("raw_record", dict(normalized))
        return normalized

    @field_validator("plan_slug", mode="before")
    @classmethod
    def validate_plan_slug(cls, value: object) -> str:
        return slug_like_text(value)

    @field_validator("content", mode="before")
    @classmethod
    def validate_content(cls, value: object) -> str:
        return plain_non_empty_string(value, "content")

    @field_validator("raw_record", mode="before")
    @classmethod
    def validate_mapping(cls, value: object) -> dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("raw_record must be an object")
        return dict(value)


    @property
    def prompt_slug(self) -> str | None:
        if self.record_identity:
            return self.record_identity.strip()

        for key in ("record_identity", "identifier", "slug", "prompt_slug"):
            value = self.raw_record.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None


__all__ = ["UploadedRecord"]
