"""Strict, canonical Git plan model. Runtime identities belong elsewhere."""

from typing import Any
import re

from pydantic import BaseModel, ConfigDict, field_validator

INSTRUCTION_PATTERN = re.compile(r"(?:rol|ctx|spc)_[0-9A-HJKMNP-TV-Z]{16}")
SCOPES = {"rol": "role", "ctx": "context", "spc": "task"}


def instruction_scope(identity: str) -> str:
    if not isinstance(identity, str) or not INSTRUCTION_PATTERN.fullmatch(identity):
        raise ValueError(f"invalid instruction identity: {identity!r}")
    return SCOPES[identity[:3]]


def validate_references(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, dict) or set(value) != set(SCOPES.values()):
        raise ValueError("instructions must contain role, context, and task arrays")
    for scope, identities in value.items():
        if not isinstance(identities, list):
            raise ValueError(f"instruction {scope} must be an array")
        for identity in identities:
            if instruction_scope(identity) != scope:
                raise ValueError(f"instruction {identity} is incompatible with {scope}")
    return value


class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    slug: str
    title: str
    description: str
    steps: dict[str, dict[str, Any]]
    capabilities: dict[str, dict[str, dict[str, Any]]]
    scope: str | None = None

    @field_validator("slug")
    @classmethod
    def valid_slug(cls, value: str) -> str:
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]*", value):
            raise ValueError("invalid plan slug")
        return value

    @field_validator("title")
    @classmethod
    def valid_title(cls, value: str) -> str:
        if not value.strip() or "\x00" in value:
            raise ValueError("plan title must be non-empty text")
        return value

    @field_validator("steps")
    @classmethod
    def valid_steps(cls, value):
        if not value or set(value) != {str(i) for i in range(1, len(value) + 1)}:
            raise ValueError("plan step ordinals must be contiguous from 1")
        allowed = {
            "engine",
            "engine_kind",
            "instructions",
            "args",
            "label",
            "model",
            "script",
            "rag_profile",
            "temperature",
            "max_output_tokens",
        }
        for ordinal, step in value.items():
            if set(step) - allowed:
                raise ValueError(
                    f"step {ordinal}: unsupported fields {set(step) - allowed}"
                )
            if not {"engine", "engine_kind", "instructions", "args"} <= set(step):
                raise ValueError(f"step {ordinal}: missing canonical fields")
            if (
                not isinstance(step["engine"], str)
                or not step["engine"]
                or step["engine"] != step["engine"].strip()
            ):
                raise ValueError(f"step {ordinal}: engine must be an explicit key")
            if step["engine_kind"] not in {"llm", "script", "rag"}:
                raise ValueError(f"step {ordinal}: invalid engine_kind")
            if not isinstance(step["args"], dict):
                raise ValueError(f"step {ordinal}: args must be an object")
            if "label" in step and not isinstance(step["label"], str):
                raise ValueError(f"step {ordinal}: label must be text")
            validate_references(step["instructions"])
        return value

    @property
    def identity(self) -> str:
        return self.slug

    @property
    def total_steps(self) -> int:
        return len(self.steps)

    def step_definition(self, step_number: int) -> dict[str, Any]:
        return dict(self.steps[str(step_number)])

    def step_args(self, step_number: int) -> dict[str, Any]:
        return dict(self.step_definition(step_number)["args"])

    def step_engine(self, step_number: int) -> str:
        return self.step_definition(step_number)["engine"]

    def plan_dict(self) -> dict[str, Any]:
        return self.model_dump()
