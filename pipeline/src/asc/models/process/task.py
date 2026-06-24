"""Short-lived daemon task, daemon outcomes, and daemon-boundary failure records."""

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
    """Uniform daemon completion envelope consumed by orchestrator.

    Outcome is orchestration state. It tells orchestrator which task completed,
    whether it succeeded, and where the daemon wrote the concrete artifact.

    Worker success points result_key at response/transform/retrieval.
    Worker failure points failure_key at failure.
    Scrivener success may have no result_key because the ledger write itself is
    the useful side effect.
    """

    model_config = ConfigDict(extra="forbid")

    kind: ClassVar[str] = "outcome"

    identity: str
    task_identity: str
    task_key: str

    package: TaskPackage
    action: str
    status: OutcomeStatus

    data_key: str | None = None
    step_key: str | None = None
    step_number: int | None = None

    result_key: str | None = None
    failure_key: str | None = None

    error: str | None = None
    error_type: str | None = None
    boundary: str | None = None

    completed_at: int = Field(default_factory=timestamp)

    @classmethod
    def success(
        cls,
        *,
        task_key: str,
        task: ScrivenerTask | WorkerTask,
        result_key: str | None = None,
        step_number: int | None = None,
    ) -> Self:
        return cls.model_validate(
            {
                "identity": task.identity,
                "task_identity": task.identity,
                "task_key": task_key,
                "package": task.package,
                "action": task.action,
                "status": "success",
                "data_key": task.data_key,
                "step_key": task.step_key if isinstance(task, WorkerTask) else None,
                "step_number": step_number,
                "result_key": result_key,
            }
        )

    @classmethod
    def failure(
        cls,
        *,
        task_key: str,
        task: ScrivenerTask | WorkerTask,
        failure_key: str,
        error: str | None = None,
        error_type: str | None = None,
        boundary: str | None = None,
        step_number: int | None = None,
    ) -> Self:
        return cls.model_validate(
            {
                "identity": task.identity,
                "task_identity": task.identity,
                "task_key": task_key,
                "package": task.package,
                "action": task.action,
                "status": "failure",
                "data_key": task.data_key,
                "step_key": task.step_key if isinstance(task, WorkerTask) else None,
                "step_number": step_number,
                "failure_key": failure_key,
                "error": error,
                "error_type": error_type,
                "boundary": boundary,
            }
        )

    @field_validator("identity", "task_identity", mode="before")
    @classmethod
    def validate_identity_segment(cls, value: object) -> str:
        return redis_key_segment_text(value, "identity")

    @field_validator("action", mode="before")
    @classmethod
    def validate_action(cls, value: object) -> str:
        return redis_key_segment_text(value, "action")

    @field_validator(
        "task_key",
        "data_key",
        "step_key",
        "result_key",
        "failure_key",
        "error",
        "error_type",
        "boundary",
        mode="before",
    )
    @classmethod
    def validate_optional_text(cls, value: object) -> str | None:
        return _optional_text(value)

    @field_validator("step_number", mode="before")
    @classmethod
    def validate_step_number(cls, value: object) -> int | None:
        if value is None or value == "":
            return None
        return int(value)

    @field_validator("completed_at", mode="before")
    @classmethod
    def validate_completed_at(cls, value: object) -> int:
        if value is None or value == "":
            return timestamp()
        return int(value)

    @field_serializer(
        "data_key",
        "step_key",
        "result_key",
        "failure_key",
        "error",
        "error_type",
        "boundary",
    )
    def serialize_optional_text(self, value: str | None) -> str:
        return "" if value is None else value

    @field_serializer("step_number")
    def serialize_step_number(self, value: int | None) -> str:
        return "" if value is None else str(value)

    @field_serializer("completed_at")
    def serialize_completed_at(self, value: int) -> str:
        return str(value)


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


def _optional_text(value: object) -> str | None:
    if value is None or value == "":
        return None

    text = str(value).strip()
    if not text:
        return None

    return text


__all__ = [
    "Failure",
    "Outcome",
    "OutcomeStatus",
    "ScrivenerTask",
    "Task",
    "TaskPackage",
    "TaskStatus",
    "WorkerTask",
]