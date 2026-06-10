from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar, Literal

from pydantic import ConfigDict, Field, field_validator

from asc.core.identity import generate_identity
from asc.models.helpers.upload import (
    OptionalRecordContent,
    RecordIdentity,
    RedisIdentity,
    record_type_text,
)
from asc.redis.model_base import RedisModel


class PlanRecord(RedisModel):
    """Uploaded reusable plan control asset.

    Plan upload records must provide the public record_* contract. The plan
    document may contain nested executable step definitions, but those are not
    written directly into the parent Redis hash. The control upload service
    validates the full document with this model, then materializes each step as
    a separate control step hash.
    """

    namespace: ClassVar[str] = "control"
    domain: ClassVar[str] = namespace
    kind: ClassVar[str] = "plan"

    model_config = ConfigDict(extra="allow")

    record_type: Literal["plan"]
    identity: RedisIdentity = Field(default_factory=generate_identity)
    record_identity: RecordIdentity
    record_content: OptionalRecordContent = ""
    steps: list[dict[str, Any]] = Field(default_factory=list)

    @property
    def slug(self) -> str:
        return self.record_identity

    @field_validator("record_type", mode="before")
    @classmethod
    def validate_record_type(cls, value: object) -> str:
        return record_type_text(value, expected=cls.kind)

    @field_validator("steps", mode="before")
    @classmethod
    def validate_steps(cls, value: object) -> list[dict[str, Any]]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("plan steps must be a list")

        steps: list[dict[str, Any]] = []
        for index, item in enumerate(value, start=1):
            if not isinstance(item, Mapping):
                raise ValueError(f"plan steps[{index}] must be an object")
            steps.append(dict(item))
        return steps

    def plan_dict(self) -> dict[str, Any]:
        """Return the full validated plan document, including nested steps."""

        return self.model_dump(mode="json")

    def dump_redis(self) -> dict[str, str]:
        """Return only scalar parent fields for the plan hash.

        Executable steps are persisted separately by asc.control.plan_steps.
        Unknown top-level plan metadata is intentionally not carried as baggage.
        """

        return {
            "record_type": self.record_type,
            "identity": self.identity,
            "record_identity": self.record_identity,
            "record_content": self.record_content,
        }


__all__ = ["PlanRecord"]
