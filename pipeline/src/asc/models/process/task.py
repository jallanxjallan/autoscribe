"""Short-lived daemon tasks and daemon outcomes."""

from __future__ import annotations

from typing import ClassVar, Literal, Self

from pydantic import ConfigDict, Field, field_serializer, field_validator

from asc.core.identity import generate_identity
from asc.core.timestamp import timestamp
from asc.models.helpers.plain import redis_key_segment_text
from asc.redis.message_base import RedisMessage


TaskPackage = Literal["worker", "scrivener"]
TaskStatus = Literal["queued", "claimed"]
OutcomeStatus = Literal["success", "failure"]


class Task(RedisMessage):
    """Short-lived instruction consumed by a daemon package.

    Task is intentionally thin. Package-specific mandatory fields live on
    ScrivenerTask and WorkerTask. Orchestrator resolves cursor/index state before
    it creates those concrete tasks.
    """

    model_config = ConfigDict(extra="forbid")

    kind: ClassVar[str] = "task"

    identity: str = Field(default_factory=generate_identity)
    package: TaskPackage
    action: str

    status: TaskStatus = "queued"
    created_at: int = Field(default_factory=timestamp)
    claimed_at: int | None = None

    @field_validator("identity", mode="before")
    @classmethod
    def validate_identity(cls, value: object) -> str:
        return redis_key_segment_text(value, "identity")

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

    @field_serializer("created_at", "claimed_at")
    def serialize_optional_int(self, value: int | None) -> str:
        return "" if value is None else str(value)


class ScrivenerTask(Task):
    """Concrete task for writing one runtime record to one ledger table."""

    package: Literal["scrivener"] = "scrivener"
    table: str
    data_key: str

    @field_validator("table", mode="before")
    @classmethod
    def validate_table(cls, value: object) -> str:
        return redis_key_segment_text(value, "table")

    @field_validator("data_key", mode="before")
    @classmethod
    def validate_data_key(cls, value: object) -> str:
        return _required_text(value, "data_key")


class WorkerTask(Task):
    """Concrete task for executing one materialized step against one data key."""

    package: Literal["worker"] = "worker"
    step_key: str
    data_key: str

    @field_validator("step_key", "data_key", mode="before")
    @classmethod
    def validate_runtime_key(cls, value: object) -> str:
        return _required_text(value, "runtime key")


class Outcome(RedisMessage):
    """Thin daemon task completion signal.

    Outcome uses the associated task identity. It does not copy task fields and
    does not carry engine-specific result payloads.
    """

    model_config = ConfigDict(extra="forbid")

    kind: ClassVar[str] = "outcome"

    identity: str
    status: OutcomeStatus
    message: str
    created_at: int = Field(default_factory=timestamp)

    @classmethod
    def success(cls, *, task: Task, message: str) -> Self:
        return cls.model_validate(
            {
                "identity": task.identity,
                "status": "success",
                "message": message,
            }
        )

    @classmethod
    def failure(cls, *, task: Task, message: str) -> Self:
        return cls.model_validate(
            {
                "identity": task.identity,
                "status": "failure",
                "message": message,
            }
        )

    @field_validator("identity", mode="before")
    @classmethod
    def validate_identity(cls, value: object) -> str:
        return redis_key_segment_text(value, "identity")

    @field_validator("status", mode="before")
    @classmethod
    def validate_status(cls, value: object) -> str:
        text = "" if value is None else str(value).strip()
        if text not in {"success", "failure"}:
            raise ValueError(f"outcome status must be success or failure: {text!r}")
        return text

    @field_validator("message", mode="before")
    @classmethod
    def validate_message(cls, value: object) -> str:
        return _required_text(value, "message")

    @field_serializer("created_at")
    def serialize_created_at(self, value: int) -> str:
        return str(value)


def _required_text(value: object, field: str) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        raise ValueError(f"{field} must not be empty")
    return text



__all__ = [
    "Outcome",
    "OutcomeStatus",
    "ScrivenerTask",
    "Task",
    "TaskPackage",
    "TaskStatus",
    "WorkerTask",
]