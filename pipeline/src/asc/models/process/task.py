"""Short-lived daemon task, success, and failure records."""

from __future__ import annotations

from typing import Any, ClassVar, Literal, Self

from pydantic import ConfigDict, Field, field_serializer, field_validator

from asc.core.identity import generate_identity
from asc.core.timestamp import timestamp
from asc.models.helpers.plain import redis_key_segment_text
from asc.redis.message_base import RedisMessage
from asc.redis.key import RedisKey


TaskPackage = Literal["worker", "scrivener"]
TaskStatus = Literal["queued", "claimed"]


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


class Committed(Task):
    """Successful task completion notice.

    The committed record copies the concrete source task under
    committed:<task_identity>. Its existence is the success signal.
    """

    kind: ClassVar[str] = "committed"

    task_identity: str
    task_key: str
    committed_at: int = Field(default_factory=timestamp)

    # Known subclass fields copied forward from ScrivenerTask/WorkerTask.
    data_key: str | None = None
    table: str | None = None
    step_key: str | None = None

    @classmethod
    def from_task(cls, task: Task, *, task_key: str) -> Self:
        return cls.model_validate(
            {
                **task.model_dump(mode="json"),
                "identity": task.identity,
                "task_identity": task.identity,
                "task_key": task_key,
            }
        )

    @field_validator("task_identity", mode="before")
    @classmethod
    def validate_task_identity(cls, value: object) -> str:
        return redis_key_segment_text(value, "task_identity")

    @field_validator("task_key", mode="before")
    @classmethod
    def validate_task_key(cls, value: object) -> str:
        return _required_text(value, "task_key")

    @field_serializer("committed_at")
    def serialize_committed_at(self, value: int) -> str:
        return str(value)

    @field_serializer("data_key", "table", "step_key")
    def serialize_optional_text(self, value: str | None) -> str:
        return "" if value is None else str(value)


class Failure(RedisMessage):
    """Arbitrary emergency/debug record for failed daemon boundaries.

    Failure is intentionally permissive. Normal routing should only need the key
    kind and identity; humans inspect the rest when something breaks.
    """

    model_config = ConfigDict(extra="allow")

    kind: ClassVar[str] = "failure"

    identity: str
    task_identity: str | None = None
    task_key: str | None = None
    package: str | None = None
    action: str | None = None

    error: str
    error_type: str
    boundary: str
    failed_at: int = Field(default_factory=timestamp)

    @classmethod
    def from_exception(
        cls,
        *,
        task_key: str,
        task: Task | None,
        exc: Exception,
        boundary: str,
        **extra: Any,
    ) -> Self:
        if task is None:
            identity = RedisKey(task_key).identity
            payload: dict[str, Any] = {}
        else:
            identity = task.identity
            payload = task.model_dump(mode="json")

        return cls.model_validate(
            {
                **payload,
                **extra,
                "identity": identity,
                "task_identity": identity,
                "task_key": task_key,
                "package": getattr(task, "package", None) or extra.get("package"),
                "action": getattr(task, "action", None) or extra.get("action"),
                "error": str(exc),
                "error_type": type(exc).__name__,
                "boundary": boundary,
            }
        )

    @field_validator("identity", mode="before")
    @classmethod
    def validate_identity(cls, value: object) -> str:
        return redis_key_segment_text(value, "identity")

    @field_validator("failed_at", mode="before")
    @classmethod
    def validate_failed_at(cls, value: object) -> int:
        if value is None or value == "":
            return timestamp()
        return int(value)

    @field_serializer("failed_at")
    def serialize_failed_at(self, value: int) -> str:
        return str(value)


def _required_text(value: object, field: str) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        raise ValueError(f"{field} must not be empty")
    return text


__all__ = [
    "Committed",
    "Failure",
    "ScrivenerTask",
    "Task",
    "TaskPackage",
    "TaskStatus",
    "WorkerTask",
]
