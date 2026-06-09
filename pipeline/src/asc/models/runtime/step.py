from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from asc.core.timestamp import timestamp
from asc.models.helpers.plain import plain_non_empty_string, positive_int, redis_key_segment_text, string_list
from asc.redis.key import RedisKey
from asc.redis.model_base import RedisModel


ControlKeyResolver = Callable[[str, str], str]


class RuntimeStepDefinition(BaseModel):
    """Worker-ready executable step definition.

    Only engine/instruction pointers are contract fields. Everything else is
    pass-through step metadata in model_extra.
    """

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


class RuntimeStepRef(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: Literal["runtime-step-ref"] = "runtime-step-ref"
    record_type: Literal["runtime-step"] = "runtime-step"
    identity: str
    step_number: int = Field(ge=1)


class RuntimeStepRecord(RedisModel):
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

    @property
    def input_position(self) -> int:
        return self.step_number

    @property
    def output_position(self) -> int:
        return self.step_number + 1

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

    @classmethod
    def key_for_step(cls, identity: str, step_number: int) -> RedisKey:
        return RedisKey.from_parts(cls.domain, redis_key_segment_text(identity, "identity"), f"{cls.kind}.{positive_int(step_number, 'step_number')}")

    @classmethod
    def key_for_identity(cls, identity: str) -> RedisKey:
        raise TypeError("RuntimeStepRecord requires step_number; use key_for_step(identity, step_number)")

    @property
    def redis_key(self) -> RedisKey:
        return self.key_for_step(self.identity, self.step_number)

    def to_ref(self) -> RuntimeStepRef:
        return RuntimeStepRef(identity=self.identity, step_number=self.step_number)

    @classmethod
    def load(cls, identity: str, step_number: int, *, require: bool = True) -> "RuntimeStepRecord | None":
        key = cls.key_for_step(identity, step_number)
        raw = key.get()
        if raw is None:
            if require:
                raise RuntimeError(f"Redis JSON record missing: {key}")
            return None
        return cls.model_validate_json(raw)

    @classmethod
    def load_from_key(cls, full_key: str | RedisKey, *, require: bool = True) -> "RuntimeStepRecord | None":
        key = full_key if isinstance(full_key, RedisKey) else RedisKey(str(full_key))
        raw = key.get()
        if raw is None:
            if require:
                raise RuntimeError(f"Redis JSON record missing: {key}")
            return None
        return cls.model_validate_json(raw)

    @classmethod
    def load_from_ref(cls, ref: RuntimeStepRef, *, require: bool = True) -> "RuntimeStepRecord | None":
        return cls.load(ref.identity, ref.step_number, require=require)

    def materialize(self) -> dict[str, Any]:
        from asc.models.runtime.content import RuntimeContentRecord
        from asc.state.runtime_indices import RuntimeContentIndex, RuntimeStepIndex

        content_index = RuntimeContentIndex(self.identity)
        input_key = content_index.resolve_key(self.input_position)
        input_record = RuntimeContentRecord.load_from_key(input_key)
        if input_record is None:
            raise RuntimeError(f"input content missing for step {self.step_number}")

        step_index = RuntimeStepIndex(self.identity)
        try:
            next_step_key = step_index.resolve_key(self.step_number + 1)
        except KeyError:
            next_step_key = None

        definition = dict(self.definition)
        return {
            "step": self,
            "step_key": str(self.redis_key),
            "step_ref": self.to_ref(),
            "definition": definition,
            "engine": definition["engine"],
            "instruction_keys": list(definition.get("instruction_keys", [])),
            "args": dict(definition.get("args", {})),
            "input_key": input_key,
            "input_record": input_record,
            "input_content": input_record.content,
            "output_position": self.output_position,
            "output_key": RuntimeContentRecord.key_for_step_result(identity=self.identity, step_number=self.step_number),
            "next_step_key": next_step_key,
            "is_terminal": next_step_key is None,
        }


def build_runtime_step_definition(step: Mapping[str, Any], *, resolve_control_key: ControlKeyResolver) -> dict[str, Any]:
    return RuntimeStepDefinition.model_validate(dict(step)).resolved(resolve_control_key=resolve_control_key).to_runtime_dict()


def build_runtime_step_records(*, identity: str, steps: Sequence[Mapping[str, Any]], resolve_control_key: ControlKeyResolver) -> list[RuntimeStepRecord]:
    return [
        RuntimeStepRecord.from_plan_step(identity=identity, step_number=offset, step=step, resolve_control_key=resolve_control_key)
        for offset, step in enumerate(steps, start=1)
    ]


__all__ = [
    "ControlKeyResolver",
    "RuntimeStepDefinition",
    "RuntimeStepRecord",
    "RuntimeStepRef",
    "build_runtime_step_definition",
    "build_runtime_step_records",
]
