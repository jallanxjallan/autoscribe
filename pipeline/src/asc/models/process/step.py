"""Short-lived executable step records."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, ClassVar

from pydantic import ConfigDict, Field, field_serializer, field_validator, model_validator

from asc.core.identity import generate_identity
from asc.core.timestamp import timestamp
from asc.models.helpers.plain import redis_key_segment_text
from asc.redis.message_base import RedisMessage


INSTRUCTION_SENTINEL = "\n\n--- ASC INSTRUCTION ---\n\n"


class Step(RedisMessage):
    """Materialized worker instruction for one plan step.

    A Step is the compiled runtime form of one plan step. It is reusable across
    calls. Workers receive the Step key plus whatever call/data key is carried
    by the WorkerTask.

    Step keys use the Plan identity plus the numeric step suffix:

        step:<plan_identity>:<step_number>

    The step number is also stored as data for workers and ledger writes.

    Plan step definitions are flattened into top-level Step attributes before
    validation. This intentionally avoids args_json/instructions_json packing.
    The plan contract must ensure that nested fields do not collide after
    flattening.
    """

    model_config = ConfigDict(extra="allow")

    kind: ClassVar[str] = "step"
    instruction_sentinel: ClassVar[str] = INSTRUCTION_SENTINEL

    identity: str = Field(default_factory=generate_identity)
    suffix: str

    step_number: int

    executor: str
    action: str
    instructions: str = ""

    created_at: int = Field(default_factory=timestamp)

    @classmethod
    def from_step_definition(
        cls,
        *,
        step_number: object,
        step_definition: Mapping[str, Any],
        identity: object | None = None,
    ) -> "Step":
        """Build a Step from one plan step definition.

        The plan step definition is unpacked directly into Step attributes.
        The Step identity should normally be the Plan identity. The suffix is
        the numeric step number.
        """

        data: dict[str, Any] = dict(step_definition)
        data["step_number"] = step_number
        data["suffix"] = str(step_number)

        if identity is not None:
            data["identity"] = identity

        return cls(**data)

    @model_validator(mode="before")
    @classmethod
    def flatten_step_definition(cls, value: object) -> object:
        if not isinstance(value, Mapping):
            return value

        flattened: dict[str, Any] = {}

        def add_field(field_name: object, field_value: Any) -> None:
            name = _attribute_name(field_name)

            if isinstance(field_value, Mapping):
                for nested_name, nested_value in field_value.items():
                    add_field(nested_name, nested_value)
                return

            if name in flattened:
                raise ValueError(f"duplicate step field after flattening: {name!r}")

            flattened[name] = field_value

        for key, item in value.items():
            add_field(key, item)

        return flattened

    @field_validator("identity", mode="before")
    @classmethod
    def validate_identity(cls, value: object) -> str:
        return redis_key_segment_text(value, "identity")

    @field_validator("suffix", mode="before")
    @classmethod
    def validate_suffix(cls, value: object) -> str:
        number = int(value)
        if number < 1:
            raise ValueError("step suffix must be >= 1")
        return str(number)

    @field_validator("executor", "action", mode="before")
    @classmethod
    def validate_required_text(cls, value: object) -> str:
        text = "" if value is None else str(value).strip()
        if not text:
            raise ValueError("executor/action must be non-empty")
        return text

    @field_validator("step_number", mode="before")
    @classmethod
    def validate_step_number(cls, value: object) -> int:
        number = int(value)
        if number < 1:
            raise ValueError("step_number must be >= 1")
        return number

    @field_validator("instructions", mode="before")
    @classmethod
    def validate_instructions(cls, value: object) -> str:
        if value is None:
            return ""

        if isinstance(value, str):
            return value

        if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
            return cls.instruction_sentinel.join(str(item) for item in value)

        return str(value)

    @field_serializer("created_at", "step_number")
    def serialize_ints(self, value: int) -> str:
        return str(value)


def _attribute_name(value: object) -> str:
    text = "" if value is None else str(value).strip()

    if not text:
        raise ValueError("step field names must be non-empty")

    if not text.isidentifier():
        raise ValueError(f"step field name must be a valid attribute name: {text!r}")

    if text.startswith("__"):
        raise ValueError(f"step field name cannot be private/dunder: {text!r}")

    return text


__all__ = ["INSTRUCTION_SENTINEL", "Step"]
