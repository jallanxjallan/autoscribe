import json
from collections.abc import Mapping
from typing import Any, ClassVar

from pydantic import ConfigDict, Field, field_serializer, field_validator, model_validator

from asc.core.identity import generate_identity
from asc.models.helpers.upload import OptionalRecordContent, RecordIdentity, RedisIdentity
from asc.redis.key import RedisKey
from asc.redis.model_base import RedisModel


def _json_text(value: object, *, default: str) -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _json_list(value: object, *, field_name: str) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, str):
        value = json.loads(value or "[]")
    if not isinstance(value, list):
        raise ValueError(f"plan {field_name} must be a list")
    return value


def _indexed_object(value: object, *, field_name: str) -> dict[int, dict[str, Any]]:
    """Normalize a 1-based indexed object, accepting legacy lists at intake."""

    if value is None:
        return {}
    if isinstance(value, str):
        value = json.loads(value or "{}")

    if isinstance(value, list):
        value = {index: item for index, item in enumerate(value, start=1)}

    if not isinstance(value, Mapping):
        raise ValueError(f"plan {field_name} must be an indexed object")

    result: dict[int, dict[str, Any]] = {}
    for raw_index, raw_item in value.items():
        if isinstance(raw_index, bool):
            raise ValueError(f"plan {field_name} key must be a positive integer")
        try:
            index = int(raw_index)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"plan {field_name} key must be a positive integer: {raw_index!r}") from exc
        if index < 1:
            raise ValueError(f"plan {field_name} key must be positive: {index}")
        if index in result:
            raise ValueError(f"plan {field_name} contains duplicate index: {index}")
        if not isinstance(raw_item, Mapping):
            raise ValueError(f"plan {field_name}[{index}] must be an object")
        result[index] = dict(raw_item)

    return dict(sorted(result.items()))


class Plan(RedisModel):
    """Uploaded reusable plan control asset."""

    kind: ClassVar[str] = "plan"
    component: ClassVar[str] = "record"

    model_config = ConfigDict(extra="ignore")

    identity: RedisIdentity = Field(default_factory=generate_identity)
    slug: RecordIdentity
    content: OptionalRecordContent = ""

    instructions: list[Any] = Field(default_factory=list, exclude=True)
    instructions_json: str = ""

    metadata_json: str = "{}"

    steps: dict[int, dict[str, Any]] = Field(default_factory=dict, exclude=True)
    steps_json: str = ""

    @model_validator(mode="before")
    @classmethod
    def normalize_plan_payload(cls, value: object) -> object:
        if not isinstance(value, Mapping):
            return value

        data = dict(value)

        if "record_content" in data:
            raw_content = data.get("record_content")
            payload = json.loads(raw_content) if isinstance(raw_content, str) and raw_content.strip() else raw_content
            if not isinstance(payload, Mapping):
                raise ValueError("plan record_content must decode to an object")

            payload_data = dict(payload)
            if "record_identity" in data:
                payload_data["slug"] = data["record_identity"]
            payload_data["content"] = raw_content if isinstance(raw_content, str) else _json_text(raw_content, default="{}")
            payload_data.pop("identity", None)
            data = payload_data

        if "record_identity" in data and "slug" not in data:
            data["slug"] = data["record_identity"]

        declared = {
            "type",
            "identity",
            "slug",
            "content",
            "instructions",
            "instructions_json",
            "metadata_json",
            "steps",
            "steps_json",
        }

        if "instructions" in data and "instructions_json" not in data:
            data["instructions_json"] = data["instructions"]

        if "steps" in data and "steps_json" not in data:
            data["steps_json"] = data["steps"]

        if "steps" not in data and "steps_json" in data:
            data["steps"] = data["steps_json"]

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

    @field_validator("instructions", mode="before")
    @classmethod
    def validate_instructions(cls, value: object) -> list[Any]:
        return _json_list(value, field_name="instructions")

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
    def validate_steps(cls, value: object) -> dict[int, dict[str, Any]]:
        return _indexed_object(value, field_name="steps")

    @field_validator("steps_json", mode="before")
    @classmethod
    def validate_steps_json(cls, value: object) -> str:
        return _json_text(value, default="[]")

    @field_serializer(
        "instructions_json",
        "metadata_json",
        "steps_json",
        when_used="json",
    )
    def serialize_json_text(self, value: str) -> str:
        return value

    @property
    def key(self) -> RedisKey:
        return self.redis_key

    @property
    def record_key(self) -> str:
        return f"plan:{self.identity}:record"

    @property
    def index_key(self) -> str:
        return f"plan:{self.identity}:index"

    @property
    def record_identity(self) -> str:
        return self.slug

    @property
    def record_content(self) -> str:
        return self.content

    @property
    def total_steps(self) -> int:
        return len(self.steps)

    def step_definition(self, step_number: int) -> dict[str, Any]:
        if step_number < 1:
            raise IndexError(f"step_number must be >= 1, got {step_number}")
        try:
            return dict(self.steps[step_number])
        except KeyError as exc:
            raise IndexError(f"plan {self.slug} has no step {step_number}; total_steps={self.total_steps}") from exc

    def step_args(self, step_number: int) -> dict[str, Any]:
        args = self.step_definition(step_number).get("args", {})
        if args is None:
            return {}
        if not isinstance(args, Mapping):
            raise ValueError(f"plan step {step_number} args must be an object")
        return dict(args)

    def step_engine(self, step_number: int) -> str:
        step = self.step_definition(step_number)
        args = self.step_args(step_number)

        engine = step.get("engine", args.get("engine"))
        if isinstance(engine, Mapping):
            engine = engine.get("key") or engine.get("module")
        if not isinstance(engine, str) or not engine.strip():
            raise ValueError(f"plan step {step_number} must provide an engine")
        return engine.strip()

    def plan_dict(self) -> dict[str, Any]:
        data = self.model_dump(mode="json")
        data["record_type"] = self.kind
        data["record_identity"] = self.slug
        data["record_content"] = self.content
        data["instructions"] = list(self.instructions)
        data["steps"] = {str(index): dict(step) for index, step in self.steps.items()}

        metadata = json.loads(self.metadata_json or "{}")
        if isinstance(metadata, dict):
            data.update(metadata)
        return data

    def dump_json(self) -> dict[str, str]:
        return {
            "type": self.kind,
            "identity": self.identity,
            "slug": self.slug,
            "content": self.content,
            "instructions_json": self.instructions_json,
            "metadata_json": self.metadata_json,
            "steps_json": self.steps_json,
        }


PlanRecord = Plan


__all__ = ["Plan", "PlanRecord"]
