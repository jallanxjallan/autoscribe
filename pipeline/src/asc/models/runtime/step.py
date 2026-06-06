from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from asc.core.timestamp import timestamp
from asc.models.control.plan import PlanStep
from asc.redis.key import RedisKey
from asc.redis.model_base import RedisModel


ControlKeyResolver = Callable[[str, str], str]


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

    Runtime step definitions contain worker-ready execution specs. Instruction
    references are resolved to full control keys during enqueue. Script steps
    carry their engine/script pointers directly from the uploaded plan.
    """

    model_config = ConfigDict(extra="ignore")

    domain: ClassVar[str] = "call"
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
        return dict(value)

    @property
    def input_position(self) -> int:
        """Content position consumed by this step."""

        return self.step_number

    @property
    def output_position(self) -> int:
        """Content position produced by this step."""

        return self.step_number + 1

    @classmethod
    def from_uploaded_step(
        cls,
        *,
        identity: str,
        step_number: int,
        step: Mapping[str, Any] | PlanStep,
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

    @classmethod
    def key_for_step(cls, identity: str, step_number: int) -> RedisKey:
        identity = cls._require_text(identity, field_name="identity")
        if not isinstance(step_number, int) or step_number < 1:
            raise ValueError("step_number must be an int >= 1")
        return RedisKey.from_parts(cls.domain, identity, cls.kind, str(step_number))

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
        return RuntimeStepRef(
            identity=self.identity,
            step_number=self.step_number,
        )

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
        return cls.load(
            ref.identity,
            ref.step_number,
            require=require,
        )

    def materialize(self) -> dict[str, Any]:
        """
        Load the runtime data needed to execute this step.

        The worker should call this instead of interpreting Redis keys or
        separately resolving content positions. Runtime indices store full Redis
        key strings; the step number is read from this JSON record.
        """

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
            "kind": self.definition.get("kind"),
            "engine": self.definition.get("engine"),
            "script": self.definition.get("script"),
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
    step: Mapping[str, Any] | PlanStep,
    *,
    resolve_control_key: ControlKeyResolver,
) -> dict[str, Any]:
    """Resolve one source/plan step into a worker-ready runtime step spec."""

    source_step = step if isinstance(step, PlanStep) else PlanStep.model_validate(step)

    kind = str(source_step.kind or "").strip().lower()
    if not kind:
        raise ValueError("plan step kind is required")

    instruction_slugs = _instruction_slugs_for_step(source_step)
    instruction_keys = [
        _resolve_instruction_key(slug, resolve_control_key=resolve_control_key)
        for slug in instruction_slugs
    ]

    args = dict(source_step.args or {})

    if kind == "script":
        engine = _require_args_text(args, "engine")
        script = _require_args_text(args, "script")

        return {
            "kind": "script",
            "engine": engine,
            "script": script,
            "instruction_keys": instruction_keys,
            "args": args,
        }

    if kind == "llm":
        engine = _require_args_text(args, "engine")

        return {
            "kind": "llm",
            "engine": engine,
            "instruction_keys": instruction_keys,
            "args": args,
        }

    raise ValueError(f"unsupported plan step kind: {kind!r}")


def build_runtime_step_records(
    *,
    identity: str,
    steps: Sequence[Mapping[str, Any] | PlanStep],
    resolve_control_key: ControlKeyResolver,
) -> list[RuntimeStepRecord]:
    return [
        RuntimeStepRecord.from_uploaded_step(
            identity=identity,
            step_number=offset,
            step=step,
            resolve_control_key=resolve_control_key,
        )
        for offset, step in enumerate(steps, start=1)
    ]


def _instruction_slugs_for_step(step: PlanStep) -> list[str]:
    raw_slugs = getattr(step, "instruction_slugs", None)

    if raw_slugs is None:
        raw_slugs = []

    if not isinstance(raw_slugs, list):
        raise ValueError("instruction_slugs must be a list")

    slugs: list[str] = []
    for value in raw_slugs:
        if not isinstance(value, str):
            raise ValueError("instruction_slugs must contain only strings")
        slug = value.strip()
        if slug:
            slugs.append(slug)

    return slugs


def _require_args_text(args: Mapping[str, Any], field_name: str) -> str:
    value = args.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"plan step requires args.{field_name}")
    return value.strip()


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
    # Already-resolved runtime specs may carry full keys. Do not run those
    # through the slug map; just validate key shape/existence/kind in the
    # resolver supplied by enqueue.
    return resolve_control_key(value, expected_kind)


__all__ = [
    "ControlKeyResolver",
    "RuntimeStepRecord",
    "RuntimeStepRef",
    "build_runtime_step_definition",
    "build_runtime_step_records",
]