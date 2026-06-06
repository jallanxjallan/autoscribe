from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import ConfigDict, Field, field_validator, model_validator

from asc.redis.model_base import RedisModel
from asc.models.helpers.upload import populate_identity_from_identifier
from asc.core.identity import generate_identity


class PlanStep(RedisModel):
    model_config = ConfigDict(extra="allow")

    index: int
    kind: str = "script"
    label: str = ""
    instructions: list[dict[str, Any]] = Field(default_factory=list)
    instruction_slugs: list[str] = Field(default_factory=list)
    args: dict[str, Any] = Field(default_factory=dict)
    engine: dict[str, Any] | None = None
    script: dict[str, Any] | None = None
    rag_profile: dict[str, Any] | None = None

    @field_validator("kind", "label", mode="before")
    @classmethod
    def clean_text(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator("instruction_slugs", mode="before")
    @classmethod
    def clean_instruction_slugs(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise TypeError("instruction_slugs must be a list")
        return [str(item).strip() for item in value if str(item or "").strip()]

    @model_validator(mode="after")
    def validate_step(self) -> "PlanStep":
        kind = self.kind.lower()

        if kind == "script":
            engine = str(self.args.get("engine") or "").strip()
            script = str(self.args.get("script") or "").strip()
            if not engine:
                raise ValueError("script step requires args.engine")
            if not script:
                raise ValueError("script step requires args.script")

        return self


class PlanRecord(RedisModel):
    namespace: ClassVar[str] = "control"
    domain: ClassVar[str] = namespace
    kind: ClassVar[str] = "plan"

    model_config = ConfigDict(extra="ignore")

    type: Literal["plan"]
    identity: str = Field(default_factory=generate_identity)
    identifier: str
    slug: str
    label: str = ""
    description: str = ""
    version: int = 1
    step_count: int | None = None
    steps: list[PlanStep]
    source: dict[str, Any] = Field(default_factory=dict)
    raw_record: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def prepare_record(cls, value: object) -> object:
        return populate_identity_from_identifier(value)

    @field_validator("slug", "label", "description", mode="before")
    @classmethod
    def clean_text(cls, value: Any) -> str:
        return str(value or "").strip()

    @model_validator(mode="after")
    def validate_plan(self) -> "PlanRecord":
        if not self.slug:
            raise ValueError("slug is required")
        if not self.slug.startswith("plan."):
            raise ValueError("slug must start with plan.")
        if not self.steps:
            raise ValueError("plan must contain at least one step")
        if self.step_count is not None and self.step_count != len(self.steps):
            raise ValueError(
                f"step_count={self.step_count} does not match steps={len(self.steps)}"
            )
        if not self.identifier:
            self.identifier = self.slug
        return self


__all__ = ["PlanRecord", "PlanStep"]