from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from asc.core.timestamp import timestamp
from asc.models.helpers.plain import plain_non_empty_string, slug_like_text, string_list
from asc.redis.key import RedisKey
from asc.redis.model_base import RedisModel


ControlKeyResolver = Callable[[str, str], str]


class RuntimeStepDefinition(BaseModel):
    """Worker-ready executable step definition.

    This is the single semantic validator for plan step objects. It accepts the
    uploaded/source shape, normalizes engine references, resolves instruction
    slugs outside the model, and preserves engine-specific fields in args.
    """

    contract_keys: ClassVar[set[str]] = {
        "engine",
        "instruction_slugs",
        "instructions",
        "instruction_keys",
        "args",
    }

    model_config = ConfigDict(extra="ignore")

    engine: str
    instructions: list[str] = Field(default_factory=list)
    instruction_keys: list[str] = Field(default_factory=list)
    args: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def normalize_step_shape(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value

        normalized = dict(value)

        if "engine" not in normalized:
            raise ValueError("step must include engine")

        if "instruction_slugs" in normalized:
            normalized.setdefault(
                "instructions",
                string_list(normalized["instruction_slugs"], "instruction_slugs"),
            )
        else:
            normalized.setdefault("instructions", [])

        normalized.setdefault("instruction_keys", [])

        explicit_args = normalized.get("args")
        if explicit_args is None:
            explicit_args = {}
        if not isinstance(explicit_args, dict):
            raise ValueError("step args must be an object")

        arbitrary_args = {
            key: item
            for key, item in normalized.items()
            if key not in cls.contract_keys
        }
        normalized["args"] = {**arbitrary_args, **explicit_args}

        return normalized

    @field_validator("engine", mode="before")
    @classmethod
    def validate_engine(cls, value: object) -> str:
        if isinstance(value, dict):
            value = value.get("key") or value.get("module") or value.get("label")
        return plain_non_empty_string(value, "engine")

    @field_validator("instructions", mode="before")
    @classmethod
    def validate_instructions(cls, value: object) -> list[str]:
        slugs = string_list(value, "instructions")
        return [slug_like_text(slug) for slug in slugs]

    @field_validator("instruction_keys", mode="before")
    @classmethod
    def validate_instruction_keys(cls, value: object) -> list[str]:
        if value is None:
            return []
        keys = string_list(value, "instruction_keys")
        return [plain_non_empty_string(key, "instruction_keys") for key in keys]

    @field_validator("args", mode="before")
    @classmethod
    def validate_args(cls, value: object) -> dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("step args must be an object")
        return dict(value)

    def resolved(self, *, resolve_control_key: ControlKeyResolver) -> "RuntimeStepDefinition":
        instruction_keys = list(self.instruction_keys)
        instruction_keys.extend(
            _resolve_instruction_key(slug, resolve_control_key=resolve_control_key)
            for slug in self.instructions
        )

        return self.model_copy(update={"instructions": [], "instruction_keys": instruction_keys})

    def to_runtime_dict(self) -> dict[str, Any]:
        return {
            "engine": self.engine,
            "instruction_keys": list(self.instruction_keys),
            "args": dict(self.args),
        }


class RuntimeStepRef(BaseModel):
    """Compatibility reference shape for old callers while queues store keys."""

    model_config = ConfigDict(extra="ignore")

    type: Literal["runtime-step-ref"] = "runtime-step-ref"
    record_type: Literal["runtime-step"] = "runtime-step"
    identity: str
    step_number: int = Field(ge=1)


class RuntimeStepRecord(RedisModel):
    """
    Redis-persisted executable step definition.

    Runtime step definitions carry a direct engine selector plus resolved
    instruction keys. Drivers are no longer part of the runtime contract.
    """

    model_config = ConfigDict(extra="ignore")

    domain: ClassVar[str] = "runtime"
    kind: ClassVar[str] = "step"

    type: Literal["runtime-step"] = "runtime-step"
    identity: str
    step_number: int = Field(ge=1)
    definition: dict[str, Any]
    created_at: int = Field(default_factory=timestamp)

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
            definition=build_runtime_step_definition(
                step,
                resolve_control_key=resolve_control_key,
            ),
        )

    # Transitional alias while callers are renamed.
    from_uploaded_step = from_plan_step

    @classmethod
    def key_for_step(cls, identity: str, step_number: int) -> RedisKey:
        identity = cls._require_text(identity, field_name="identity")
        if not isinstance(step_number, int) or step_number < 1:
            raise ValueError("step_number must be an int >= 1")
        return RedisKey.from_parts(cls.domain, identity, f"{cls.kind}.{step_number}")

    @classmethod
    def key_for_identity(cls, identity: str) -> RedisKey:
        raise TypeError(
            "RuntimeStepRecord requires step_number; "
            "use key_for_step(identity, step_number)"
        )

    @property
    def redis_key(self) -> RedisKey:
        return self.key_for_step(self.identity, self.step_number)

    def to_ref(self) -> RuntimeStepRef:
        return RuntimeStepRef(identity=self.identity, step_number=self.step_number)

    @classmethod
    def load(
        cls,
        identity: str,
        step_number: int,
        *,
        require: bool = True,
    ) -> "RuntimeStepRecord | None":
        key = cls.key_for_step(identity, step_number)
        raw = key.get()

        if raw is None:
            if require:
                raise RuntimeError(f"Redis JSON record missing: {key}")
            return None

        return cls.model_validate_json(raw)

    @classmethod
    def load_from_key(
        cls,
        full_key: str | RedisKey,
        *,
        require: bool = True,
    ) -> "RuntimeStepRecord | None":
        key = full_key if isinstance(full_key, RedisKey) else RedisKey(str(full_key))
        raw = key.get()

        if raw is None:
            if require:
                raise RuntimeError(f"Redis JSON record missing: {key}")
            return None

        return cls.model_validate_json(raw)

    @classmethod
    def load_from_ref(
        cls,
        ref: RuntimeStepRef,
        *,
        require: bool = True,
    ) -> "RuntimeStepRecord | None":
        return cls.load(ref.identity, ref.step_number, require=require)

    def materialize(self) -> dict[str, Any]:
        """Load the runtime data needed to execute this step."""

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

        return {
            "step": self,
            "step_key": str(self.redis_key),
            "step_ref": self.to_ref(),
            "definition": self.definition,
            "engine": self.definition["engine"],
            "instruction_keys": list(self.definition.get("instruction_keys", [])),
            "args": dict(self.definition.get("args", {})),
            "input_key": input_key,
            "input_record": input_record,
            "input_content": input_record.content,
            "output_position": self.output_position,
            "output_key": RuntimeContentRecord.key_for_step_result(
                identity=self.identity,
                step_number=self.step_number,
            ),
            "next_step_key": next_step_key,
            "is_terminal": next_step_key is None,
        }


def build_runtime_step_definition(
    step: Mapping[str, Any],
    *,
    resolve_control_key: ControlKeyResolver,
) -> dict[str, Any]:
    """Resolve one plan step into a worker-ready runtime step spec."""

    source_step = RuntimeStepDefinition.model_validate(dict(step))
    resolved_step = source_step.resolved(resolve_control_key=resolve_control_key)
    return resolved_step.to_runtime_dict()


def build_runtime_step_records(
    *,
    identity: str,
    steps: Sequence[Mapping[str, Any]],
    resolve_control_key: ControlKeyResolver,
) -> list[RuntimeStepRecord]:
    return [
        RuntimeStepRecord.from_plan_step(
            identity=identity,
            step_number=offset,
            step=step,
            resolve_control_key=resolve_control_key,
        )
        for offset, step in enumerate(steps, start=1)
    ]


def _resolve_instruction_key(
    value: str,
    *,
    resolve_control_key: ControlKeyResolver,
) -> str:
    return _resolve_control_pointer(value, "instruction", resolve_control_key=resolve_control_key)


def _resolve_control_pointer(
    value: str,
    expected_kind: str,
    *,
    resolve_control_key: ControlKeyResolver,
) -> str:
    return resolve_control_key(value, expected_kind)


__all__ = [
    "ControlKeyResolver",
    "RuntimeStepDefinition",
    "RuntimeStepRecord",
    "RuntimeStepRef",
    "build_runtime_step_definition",
    "build_runtime_step_records",
]
