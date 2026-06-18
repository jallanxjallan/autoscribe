"""Daemon outcome records."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, ClassVar, Literal

from pydantic import ConfigDict, Field, field_serializer, field_validator

from asc.core.timestamp import timestamp
from asc.models.helpers.plain import plain_non_empty_string, redis_key_segment_text
from asc.redis.message_base import RedisMessage


OutcomeStatus = Literal["completed", "failed"]


class _OutcomeBase(RedisMessage):
    """Shared shape for daemon outcomes."""

    model_config = ConfigDict(extra="forbid")

    identity: str
    task_key: str
    cursor_key: str
    action: str
    status: OutcomeStatus

    task_number: int
    step_number: int

    output_model: str
    output_key: str

    message: str
    fail_message: str
    failure_reason: str
    raw_json: Any

    created_at: int = Field(default_factory=timestamp)

    @field_validator("identity", mode="before")
    @classmethod
    def validate_identity(cls, value: object) -> str:
        return redis_key_segment_text(value, "identity")

    @field_validator("task_key", "cursor_key", "output_key", mode="before")
    @classmethod
    def validate_required_key(cls, value: object) -> str:
        text = plain_non_empty_string(value, "Redis key")
        if ":" not in text:
            raise ValueError(f"expected full Redis key, got {text!r}")
        return text

    @field_validator("action", mode="before")
    @classmethod
    def validate_action(cls, value: object) -> str:
        return redis_key_segment_text(value, "action")

    @field_validator("task_number", "step_number", mode="before")
    @classmethod
    def validate_number(cls, value: object) -> int:
        number = int(value)
        if number < 0:
            raise ValueError("task and step numbers must be >= 0")
        return number

    @field_validator("raw_json", mode="before")
    @classmethod
    def validate_raw_json(cls, value: object) -> object:
        if isinstance(value, str):
            return json.loads(value)
        if isinstance(value, Mapping):
            return dict(value)
        return value

    @field_serializer("task_number", "step_number")
    def serialize_number(self, value: int) -> str:
        return str(value)

    @field_serializer("raw_json", when_used="json")
    def serialize_raw_json(self, value: Any) -> Any:
        return value


class WorkerOutcome(_OutcomeBase):
    """Outcome posted by the worker daemon to the orchestrator."""

    kind: ClassVar[str] = "worker_outcome"


class ScrivenerOutcome(_OutcomeBase):
    """Outcome posted by the scrivener daemon to the orchestrator."""

    kind: ClassVar[str] = "scrivener_outcome"

    ledger_table: str


__all__ = ["OutcomeStatus", "ScrivenerOutcome", "WorkerOutcome"]
