"""Daemon task records.

A task is one concrete unit of work consumed by one execution daemon.
The whole call may contain many plan steps and many daemon tasks.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, ClassVar, Literal

from pydantic import ConfigDict, Field, field_serializer, field_validator

from asc.core.timestamp import timestamp
from asc.models.helpers.plain import plain_non_empty_string, redis_key_segment_text
from asc.redis.model_base import RedisModel


TaskStatus = Literal["queued", "claimed"]


class _TaskBase(RedisModel):
    """Shared shape for daemon tasks.

    ``identity`` is the call identity shared by the cursor, response index,
    results, failures, and all daemon task/outcome records.

    ``task_number`` is a daemon-local sequence number for this call. It is not
    necessarily the same as ``step_number`` because scrivener tasks may bracket
    or follow worker tasks.
    """

    model_config = ConfigDict(extra="forbid")

    identity: str
    task_number: int
    cursor_key: str
    action: str
    step_number: int = 0

    input_model: str = ""
    input_key: str = ""
    output_model: str = ""
    output_key: str = ""

    engine: str = ""
    handler: str = ""
    args_json: str = "{}"

    status: TaskStatus = "queued"
    created_at: int = Field(default_factory=timestamp)
    claimed_at: int | None = None

    @field_validator("identity", mode="before")
    @classmethod
    def validate_identity(cls, value: object) -> str:
        return redis_key_segment_text(value, "identity")

    @field_validator("task_number", "step_number", mode="before")
    @classmethod
    def validate_number(cls, value: object) -> int:
        if value in (None, ""):
            return 0
        number = int(value)
        if number < 0:
            raise ValueError("task and step numbers must be >= 0")
        return number

    @field_validator("cursor_key", mode="before")
    @classmethod
    def validate_cursor_key(cls, value: object) -> str:
        text = plain_non_empty_string(value, "cursor_key")
        if ":" not in text:
            raise ValueError(f"expected full Redis key, got {text!r}")
        return text

    @field_validator("input_key", "output_key", mode="before")
    @classmethod
    def validate_optional_full_key(cls, value: object) -> str:
        if value in (None, ""):
            return ""
        text = plain_non_empty_string(value, "Redis key")
        if ":" not in text:
            raise ValueError(f"expected full Redis key, got {text!r}")
        return text

    @field_validator("action", mode="before")
    @classmethod
    def validate_action(cls, value: object) -> str:
        return redis_key_segment_text(value, "action")

    @field_validator("args_json", mode="before")
    @classmethod
    def validate_args_json(cls, value: object) -> str:
        if value in (None, ""):
            return "{}"
        if isinstance(value, str):
            json.loads(value or "{}")
            return value
        if isinstance(value, Mapping):
            return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        raise ValueError("args_json must be a JSON string or mapping")

    @field_serializer("task_number", "step_number")
    def serialize_number(self, value: int) -> str:
        return str(value)


class WorkerTask(_TaskBase):
    """Task consumed by the worker daemon."""

    kind: ClassVar[str] = "worker_task"


class ScrivenerTask(_TaskBase):
    """Task consumed by the scrivener daemon."""

    kind: ClassVar[str] = "scrivener_task"

    ledger_table: str = ""


__all__ = [
    "ScrivenerTask",
    "TaskStatus",
    "WorkerTask",
]
