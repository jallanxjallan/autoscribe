"""Typed executable step control records."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, ClassVar, Literal, Self

from pydantic import (
    AliasChoices,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from asc.core.identity import generate_identity
from asc.core.timestamp import timestamp
from asc.redis.key import RedisKey
from asc.redis.model_base import RedisModel


class Step(RedisModel):
    """Base model for a materialized executable plan step.

    Concrete subclasses define the complete contract for each engine kind.
    Redis records retain ``engine_kind`` so ``Step.load()`` can restore the
    correct subtype before the worker crosses the engine boundary.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    kind: ClassVar[str] = "step"

    identity: str = Field(default_factory=generate_identity)
    ordinal: int = Field(
        validation_alias=AliasChoices("ordinal", "step_number", "number", "index"),
    )
    engine: str
    engine_kind: Literal["llm", "script", "rag"] = Field(
        validation_alias=AliasChoices("engine_kind", "kind"),
    )
    label: str = ""
    instruction_keys: dict[str, str | list[str]] = Field(default_factory=dict)
    instruction_slugs: dict[str, str | list[str]] = Field(default_factory=dict, exclude=True)
    created_at: int = Field(default_factory=timestamp)

    @model_validator(mode="before")
    @classmethod
    def normalize_plan_shape(cls, value: object) -> object:
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

        # Older plan writers emitted an empty generic args object for every
        # step. It carries no information and is not part of the LLM/RAG
        # contracts. Non-empty args remain available only on ScriptStep.
        if data.get("args") == {}:
            data.pop("args")

        return data

    @classmethod
    def from_plan(
        cls,
        raw_step: Mapping[str, Any],
        *,
        identity: str,
        ordinal: int,
        engine: str,
        engine_kind: str,
        instruction_keys: dict[str, str | list[str]],
    ) -> Step:
        payload = {
            **raw_step,
            "identity": identity,
            "ordinal": ordinal,
            "engine": engine,
            "engine_kind": engine_kind,
            "instruction_keys": instruction_keys,
        }
        clean_kind = str(engine_kind).strip()
        model = _STEP_MODELS.get(clean_kind)
        if model is None:
            supported = ", ".join(sorted(_STEP_MODELS))
            raise ValueError(
                f"unsupported step kind {clean_kind!r}; expected one of {supported}"
            )
        return model.model_validate(payload)

    @classmethod
    def load(cls, key: str | RedisKey) -> Step:
        redis_key = cls.redis_key_from_raw(key)
        raw = redis_key.hgetall()
        if not raw:
            raise RuntimeError(f"Redis hash record missing: {redis_key.raw_key}")
        return cls.load_redis(raw)

    @classmethod
    def load_redis(cls, data: dict[str, str]) -> Step:
        engine_kind = str(data.get("engine_kind", "")).strip()
        model = _STEP_MODELS.get(engine_kind)
        if model is None:
            supported = ", ".join(sorted(_STEP_MODELS))
            raise ValueError(
                f"stored step has unsupported engine_kind {engine_kind!r}; "
                f"expected one of {supported}"
            )
        return model.model_validate(data)

    @property
    def step_number(self) -> int:
        return self.ordinal

    @field_validator("ordinal", mode="before")
    @classmethod
    def validate_ordinal(cls, value: object) -> int:
        text = "" if value is None else str(value).strip()
        if not text:
            raise ValueError("step ordinal must not be empty")
        number = int(text)
        if number < 1:
            raise ValueError(f"step ordinal must be >= 1: {number}")
        return number

    @field_validator("engine", "label", mode="before")
    @classmethod
    def validate_text(cls, value: object) -> str:
        return "" if value is None else str(value).strip()

    @field_validator("instruction_keys", "instruction_slugs", mode="before")
    @classmethod
    def deserialize_instruction_map(cls, value: object) -> dict[str, str]:
        if value in (None, ""):
            return {}
        if isinstance(value, str):
            value = json.loads(value)
        if isinstance(value, list):
            labels = ("role", "context", "instructions")
            if len(value) > len(labels):
                raise ValueError("legacy instruction list may contain at most three references")
            value = {labels[index]: item for index, item in enumerate(value)}
        if not isinstance(value, Mapping):
            raise ValueError("step instruction references must be a labeled object")
        result: dict[str, str | list[str]] = {}
        for raw_label, raw_reference in value.items():
            label = str(raw_label).strip()
            if not label:
                raise ValueError("step instruction references must use non-empty labels")

            if isinstance(raw_reference, str):
                reference = raw_reference.strip()
                if not reference:
                    raise ValueError(
                        "step instruction references must use non-empty strings"
                    )
                result[label] = reference
                continue

            if isinstance(raw_reference, list) and all(
                isinstance(item, str) for item in raw_reference
            ):
                references = [item.strip() for item in raw_reference]
                if not references or any(not item for item in references):
                    raise ValueError(
                        "step instruction lists must contain non-empty strings"
                    )
                result[label] = references
                continue

            raise ValueError(
                f"step instruction {label!r} must be a string or list of strings"
            )

        return result

    def dump_json(self) -> dict[str, str]:
        """Serialize only fields declared by the concrete step subtype."""

        dumped = self.model_dump(
            mode="json",
            exclude_none=True,
            exclude={"instruction_slugs"},
        )

        def redis_value(value: Any, *, field_name: str) -> str:
            if isinstance(value, RedisKey):
                return value.raw_key
            if isinstance(value, bool):
                return "true" if value else "false"
            if isinstance(value, (str, int, float)):
                return str(value)
            try:
                return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            except TypeError as exc:
                raise TypeError(
                    f"{field_name} could not be JSON-serialized for Redis hash storage"
                ) from exc

        return {
            field_name: redis_value(value, field_name=field_name)
            for field_name, value in dumped.items()
            if value not in ("", [], {})
        }


class LLMStep(Step):
    """Validated parameters for an LLM engine call."""

    engine_kind: Literal["llm"] = "llm"
    model: str
    temperature: float | None = None
    max_output_tokens: int | None = None

    @field_validator("model", mode="before")
    @classmethod
    def validate_model(cls, value: object) -> str:
        text = "" if value is None else str(value).strip()
        if not text:
            raise ValueError("LLM step model must not be empty")
        return text


class ScriptStep(Step):
    """Validated parameters for a local script transform."""

    engine_kind: Literal["script"] = "script"
    script: str

    @field_validator("script", mode="before")
    @classmethod
    def validate_script(cls, value: object) -> str:
        text = "" if value is None else str(value).strip()
        if not text:
            raise ValueError("script step script must not be empty")
        return text


class RAGStep(Step):
    """Validated parameters for a retrieval engine call."""

    engine_kind: Literal["rag"] = "rag"
    rag_profile: str

    @field_validator("rag_profile", mode="before")
    @classmethod
    def validate_rag_profile(cls, value: object) -> str:
        text = "" if value is None else str(value).strip()
        if not text:
            raise ValueError("RAG step rag_profile must not be empty")
        return text


_STEP_MODELS: dict[str, type[Step]] = {
    "llm": LLMStep,
    "script": ScriptStep,
    "rag": RAGStep,
}

StepType = LLMStep | ScriptStep | RAGStep


__all__ = ["LLMStep", "RAGStep", "ScriptStep", "Step", "StepType"]
