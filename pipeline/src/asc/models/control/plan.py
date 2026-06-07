from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import ConfigDict, Field, field_validator, model_validator

from asc.core.identity import generate_identity
from asc.models.helpers.plain import (
    plain_non_empty_string,
    redis_key_segment_text,
    slug_like_text,
)
from asc.redis.model_base import RedisModel


class PlanRecord(RedisModel):
    """Uploaded reusable plan control asset.

    A plan owns the wrapper contract only. Step semantics are validated later
    by the runtime step model when enqueue materializes executable steps.
    """

    namespace: ClassVar[str] = "control"
    domain: ClassVar[str] = namespace
    kind: ClassVar[str] = "plan"

    model_config = ConfigDict(extra="ignore")

    type: Literal["plan"]
    identity: str = Field(default_factory=generate_identity)
    slug: str
    title: str | None = None
    steps: list[dict[str, Any]]
    content: str = ""
    raw_record: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def normalize_upload_shape(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value

        normalized = dict(value)
        normalized.pop("identity", None)

        if "steps" not in normalized:
            for key in ("plan_steps", "job_steps"):
                if key in normalized:
                    normalized["steps"] = normalized[key]
                    break

        normalized.setdefault("raw_record", dict(normalized))
        return normalized

    @field_validator("identity", mode="before")
    @classmethod
    def validate_identity(cls, value: object) -> str:
        return redis_key_segment_text(value, "identity")

    @field_validator("slug", mode="before")
    @classmethod
    def validate_slug(cls, value: object) -> str:
        return slug_like_text(value)

    @field_validator("title", mode="before")
    @classmethod
    def validate_title(cls, value: object) -> str | None:
        if value is None:
            return None
        return plain_non_empty_string(value, "title")

    @field_validator("steps", mode="before")
    @classmethod
    def validate_steps(cls, value: object) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            raise ValueError("plan.steps must be a list")
        if not value:
            raise ValueError("plan.steps must contain at least one step")

        steps: list[dict[str, Any]] = []
        for index, item in enumerate(value, start=1):
            if not isinstance(item, dict):
                raise ValueError(f"plan.steps[{index}] must be an object")
            steps.append(dict(item))
        return steps

    @field_validator("content", mode="before")
    @classmethod
    def validate_content(cls, value: object) -> str:
        if value is None:
            return ""
        if not isinstance(value, str):
            raise ValueError("content must be a plain string")
        return value


__all__ = ["PlanRecord"]
