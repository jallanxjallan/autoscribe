"""Short-lived call-scoped executable runtime records."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, ClassVar, Literal

from pydantic import AliasChoices, ConfigDict, Field, field_validator, model_validator

from asc.redis.model_base import RedisModel


class Runtime(RedisModel):
    """One executable plan step materialized for a specific call.

    Runtime records are deliberately ephemeral. Their Redis identity is the
    call identity and their key suffix is the 1-based step ordinal:

        runtime:<call_identity>:<ordinal>
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    kind: ClassVar[str] = "runtime"

    identity: str
    plan_identity: str
    ordinal: int = Field(validation_alias=AliasChoices("ordinal", "step_number", "number", "index"))
    total_steps: int
    engine_kind: Literal["llm", "script", "rag"] = Field(validation_alias=AliasChoices("engine_kind", "kind"))
    engine: str
    label: str = ""
    instruction_keys: dict[str, str] = Field(default_factory=dict)

    model: str | None = None
    script: str | None = None
    rag_profile: str | None = None
    temperature: float | None = None
    max_output_tokens: int | None = None
    args: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def normalize_shape(cls, value: object) -> object:
        if not isinstance(value, Mapping):
            return value
        data = dict(value)
        if "engine_kind" not in data and "kind" in data:
            data["engine_kind"] = data["kind"]
        data.pop("kind", None)
        if "ordinal" not in data:
            for alias in ("step_number", "number", "index"):
                if alias in data:
                    data["ordinal"] = data[alias]
                    break
        for alias in ("step_number", "number", "index"):
            data.pop(alias, None)
        return data

    @model_validator(mode="after")
    def validate_engine_contract(self) -> "Runtime":
        if self.total_steps < self.ordinal:
            raise ValueError(
                f"runtime ordinal {self.ordinal} exceeds total_steps {self.total_steps}"
            )
        required = {
            "llm": ("model", self.model),
            "script": ("script", self.script),
            "rag": ("rag_profile", self.rag_profile),
        }
        field_name, value = required[self.engine_kind]
        if not value or not str(value).strip():
            raise ValueError(f"{self.engine_kind} runtime requires {field_name}")
        return self

    @field_validator("identity", "plan_identity", "engine", "label", mode="before")
    @classmethod
    def validate_text(cls, value: object) -> str:
        return "" if value is None else str(value).strip()

    @field_validator("ordinal", "total_steps", mode="before")
    @classmethod
    def validate_positive_int(cls, value: object) -> int:
        number = int(value)
        if number < 1:
            raise ValueError("runtime ordinal and total_steps must be positive")
        return number

    @field_validator("instruction_keys", mode="before")
    @classmethod
    def deserialize_instruction_keys(cls, value: object) -> dict[str, str]:
        if value in (None, ""):
            return {}
        if isinstance(value, str):
            value = json.loads(value)
        if not isinstance(value, Mapping):
            raise ValueError("runtime instruction_keys must be a labeled object")
        result = {str(k).strip(): str(v).strip() for k, v in value.items()}
        if any(not k or not v for k, v in result.items()):
            raise ValueError("runtime instruction_keys must use non-empty labels and keys")
        return result

    def dump_json(self) -> dict[str, str]:
        dumped = self.model_dump(mode="json", exclude_none=True)
        result: dict[str, str] = {}
        for field_name, value in dumped.items():
            if value in ("", [], {}):
                continue
            if isinstance(value, bool):
                result[field_name] = "true" if value else "false"
            elif isinstance(value, (str, int, float)):
                result[field_name] = str(value)
            else:
                result[field_name] = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        return result


__all__ = ["Runtime"]
