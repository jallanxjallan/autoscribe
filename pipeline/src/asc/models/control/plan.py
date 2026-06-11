from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, ClassVar, Literal

from pydantic import ConfigDict, Field, field_serializer, field_validator, model_validator

from asc.core.identity import generate_identity
from asc.models.helpers.upload import (
    OptionalRecordContent,
    RecordIdentity,
    RedisIdentity,
    record_type_text,
)
from asc.redis.model_base import RedisModel


def _json_text(value: object, *, default: str) -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class PlanRecord(RedisModel):
    """Uploaded reusable plan control asset."""

    namespace: ClassVar[str] = "control"
    domain: ClassVar[str] = namespace
    kind: ClassVar[str] = "plan"

    model_config = ConfigDict(extra="forbid")

    record_type: Literal["plan"]
    identity: RedisIdentity = Field(default_factory=generate_identity)
    record_identity: RecordIdentity
    record_content: OptionalRecordContent = ""

    instructions: list[Any] = Field(default_factory=list, exclude=True)
    instructions_json: str = ""
    metadata_json: str = "{}"
    steps: list[dict[str, Any]] = Field(default_factory=list, exclude=True)

    @property
    def slug(self) -> str:
        return self.record_identity

    @model_validator(mode="before")
    @classmethod
    def normalize_plan_payload(cls, value: object) -> object:
        if not isinstance(value, Mapping):
            return value

        data = dict(value)

        declared = {
            "record_type",
            "identity",
            "record_identity",
            "record_content",
            "instructions",
            "instructions_json",
            "metadata_json",
            "steps",
        }

        if "instructions" in data and "instructions_json" not in data:
            data["instructions_json"] = data["instructions"]

        metadata: dict[str, Any] = {}

        existing_metadata = data.get("metadata_json")
        if isinstance(existing_metadata, str) and existing_metadata.strip():
            try:
                parsed = json.loads(existing_metadata)
                if isinstance(parsed, dict):
                    metadata.update(parsed)
            except json.JSONDecodeError:
                metadata["_metadata_json_raw"] = existing_metadata
        elif isinstance(existing_metadata, Mapping):
            metadata.update(dict(existing_metadata))

        for key in list(data):
            if key not in declared:
                metadata[key] = data.pop(key)

        data["metadata_json"] = metadata

        return data

    @field_validator("record_type", mode="before")
    @classmethod
    def validate_record_type(cls, value: object) -> str:
        return record_type_text(value, expected=cls.kind)

    @field_validator("instructions", mode="before")
    @classmethod
    def validate_instructions(cls, value: object) -> list[Any]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("plan instructions must be a list")
        return value

    @field_validator("instructions_json", mode="before")
    @classmethod
    def validate_instructions_json(cls, value: object) -> str:
        return _json_text(value, default="[]")

    @field_validator("metadata_json", mode="before")
    @classmethod
    def validate_metadata_json(cls, value: object) -> str:
        return _json_text(value, default="{}")

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

    @field_serializer("instructions_json", "metadata_json", when_used="json")
    def serialize_json_text(self, value: str) -> str:
        return value

    def plan_dict(self) -> dict[str, Any]:
        data = self.model_dump(mode="json")
        data["instructions"] = list(self.instructions)
        data["steps"] = list(self.steps)

        metadata = json.loads(self.metadata_json or "{}")
        if isinstance(metadata, dict):
            data.update(metadata)

        return data

    def dump_redis(self) -> dict[str, str]:
        return {
            "record_type": self.record_type,
            "identity": self.identity,
            "record_identity": self.record_identity,
            "record_content": self.record_content,
            "instructions_json": self.instructions_json,
            "metadata_json": self.metadata_json,
        }


__all__ = ["PlanRecord"]