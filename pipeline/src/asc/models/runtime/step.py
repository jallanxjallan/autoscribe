from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from asc.core.timestamp import timestamp
from asc.models.helpers.plain import plain_non_empty_string, positive_int, redis_key_segment_text, string_list
from asc.redis.model_base import RedisModel


ControlKeyResolver = Callable[[str, str], str]


class RuntimeStepDefinition(BaseModel):
    """Worker-ready step definition copied from a resolved plan step."""

    model_config = ConfigDict(extra="allow")

    engine: str
    instructions: list[str] = Field(default_factory=list)
    instruction_keys: list[str] = Field(default_factory=list)
    args: dict[str, Any] = Field(default_factory=dict)

    @field_validator("engine", mode="before")
    @classmethod
    def validate_engine(cls, value: object) -> str:
        return plain_non_empty_string(value, "engine")

    @field_validator("instructions", "instruction_keys", mode="before")
    @classmethod
    def validate_string_list(cls, value: object) -> list[str]:
        return string_list(value, "instructions")

    @field_validator("args", mode="before")
    @classmethod
    def validate_args(cls, value: object) -> dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("args must be an object")
        return dict(value)

    def resolved(self, *, resolve_control_key: ControlKeyResolver) -> "RuntimeStepDefinition":
        instruction_keys = list(self.instruction_keys)
        instruction_keys.extend(resolve_control_key(slug, "instruction") for slug in self.instructions)
        return self.model_copy(update={"instructions": [], "instruction_keys": instruction_keys})

    def to_runtime_dict(self) -> dict[str, Any]:
        return {
            "engine": self.engine,
            "instruction_keys": list(self.instruction_keys),
            "args": dict(self.args),
            **dict(self.model_extra or {}),
        }


class RuntimeStepRecord(RedisModel):
    """Runtime step definition record.

    No materialize/load/ref helpers live here. Orchestrator owns positional keys,
    input/output content selection, and terminal-step detection.
    """

    model_config = ConfigDict(extra="allow")

    domain: ClassVar[str] = "runtime"
    kind: ClassVar[str] = "step"

    type: Literal["runtime-step"] = "runtime-step"
    identity: str
    step_number: int = Field(ge=1)
    definition: dict[str, Any]
    created_at: int = Field(default_factory=timestamp)

    @field_validator("identity", mode="before")
    @classmethod
    def validate_identity(cls, value: object) -> str:
        return redis_key_segment_text(value, "identity")

    @field_validator("step_number", mode="before")
    @classmethod
    def validate_step_number(cls, value: object) -> int:
        return positive_int(value, "step_number")

    @field_validator("definition", mode="before")
    @classmethod
    def validate_definition(cls, value: object) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError("runtime step definition must be an object")
        return RuntimeStepDefinition.model_validate(value).to_runtime_dict()

    @classmethod
    def from_plan_step(
        cls,
        *,
        identity: str,
        step_number: int,
        step: Mapping[str, Any],
        resolve_control_key: ControlKeyResolver,
    ) -> "RuntimeStepRecord":
        return cls(
            identity=identity,
            step_number=step_number,
            definition=build_runtime_step_definition(step, resolve_control_key=resolve_control_key),
        )

    from_uploaded_step = from_plan_step


def build_runtime_step_definition(step: Mapping[str, Any], *, resolve_control_key: ControlKeyResolver) -> dict[str, Any]:
    return RuntimeStepDefinition.model_validate(dict(step)).resolved(resolve_control_key=resolve_control_key).to_runtime_dict()


def build_runtime_step_records(*, identity: str, steps: Sequence[Mapping[str, Any]], resolve_control_key: ControlKeyResolver) -> list[RuntimeStepRecord]:
    return [
        RuntimeStepRecord.from_plan_step(
            identity=identity,
            step_number=offset,
            step=step,
            resolve_control_key=resolve_control_key,
        )
        for offset, step in enumerate(steps, start=1)
    ]


StepRecord = RuntimeStepRecord

__all__ = [
    "ControlKeyResolver",
    "RuntimeStepDefinition",
    "RuntimeStepRecord",
    "StepRecord",
    "build_runtime_step_definition",
    "build_runtime_step_records",
]
