"""Daemon task records."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import ClassVar, Literal

from pydantic import ConfigDict, Field, field_serializer, field_validator

from asc.core.timestamp import timestamp
from asc.models.helpers.plain import plain_non_empty_string, redis_key_segment_text
from asc.redis.message_base import RedisMessage


TaskStatus = Literal["queued", "claimed"]




class _TaskBase(RedisMessage):
    """Shared shape for daemon tasks."""

    model_config = ConfigDict(extra="forbid")

    identity: str
    task_number: int
    cursor_key: str

    action: str
    status: TaskStatus = "queued"

    created_at: int = Field(default_factory=timestamp)
    claimed_at: int | None = None

    @field_validator("identity", mode="before")
    @classmethod
    def validate_identity(cls, value: object) -> str:
        return redis_key_segment_text(value, "identity")

    @field_validator("task_number", mode="before")
    @classmethod
    def validate_task_number(cls, value: object) -> int:
        number = int(value)
        if number < 0:
            raise ValueError("task_number must be >= 0")
        return number

    @field_validator("cursor_key", mode="before")
    @classmethod
    def validate_cursor_key(cls, value: object) -> str:
        text = plain_non_empty_string(value, "cursor_key")
        if ":" not in text:
            raise ValueError(f"expected full Redis key, got {text!r}")
        return text

    @field_validator("action", mode="before")
    @classmethod
    def validate_action(cls, value: object) -> str:
        return redis_key_segment_text(value, "action")

    @field_validator("claimed_at", mode="before")
    @classmethod
    def validate_claimed_at(cls, value: object) -> int | None:
        if value is None or value == "":
            return None
        return int(value)

    @field_serializer("task_number")
    def serialize_task_number(self, value: int) -> str:
        return str(value)


class WorkerTask(_TaskBase):
    """Task consumed by the worker daemon."""

    kind: ClassVar[str] = "worker_task"

    step_number: int

    input_model: str
    input_key: str

    output_model: str
    output_key: str

    engine: str
    handler: str
    args_json: str

    @field_validator("step_number", mode="before")
    @classmethod
    def validate_step_number(cls, value: object) -> int:
        number = int(value)
        if number < 0:
            raise ValueError("step_number must be >= 0")
        return number

    @field_validator("input_key", "output_key", mode="before")
    @classmethod
    def validate_required_key(cls, value: object) -> str:
        text = plain_non_empty_string(value, "Redis key")
        if ":" not in text:
            raise ValueError(f"expected full Redis key, got {text!r}")
        return text

    @field_validator("args_json", mode="before")
    @classmethod
    def validate_args_json(cls, value: object) -> str:
        if isinstance(value, str):
            json.loads(value)
            return value
        if isinstance(value, Mapping):
            return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        raise ValueError("args_json must be JSON or a mapping")

    @field_serializer("step_number")
    def serialize_step_number(self, value: int) -> str:
        return str(value)


class ScrivenerTask(_TaskBase):
    """Task consumed by the scrivener daemon."""

    kind: ClassVar[str] = "scrivener_task"

    source_key: str
    ledger_table: str

    @field_validator("source_key", mode="before")
    @classmethod
    def validate_source_key(cls, value: object) -> str:
        text = plain_non_empty_string(value, "source_key")
        if ":" not in text:
            raise ValueError(f"expected full Redis key, got {text!r}")
        return text


__all__ = ["TaskStatus", "WorkerTask", "ScrivenerTask"]
