"""Short-lived daemon task and task result records."""

from __future__ import annotations

from typing import ClassVar, Literal, Self

from pydantic import Field, field_serializer, field_validator

from asc.core.identity import generate_identity
from asc.core.timestamp import timestamp
from asc.models.helpers.plain import redis_key_segment_text
from asc.redis.message_base import RedisMessage


TaskPackage = Literal["worker", "scrivener"]
TaskStatus = Literal["queued", "claimed"]
OutcomeResult = Literal["success", "failure"]


class Task(RedisMessage):
    """Short-lived instruction consumed by a daemon package.

    A task says which package should execute which action for which cursor.
    The executor loads the cursor and derives the rest from process state.
    """

    kind: ClassVar[str] = "task"

    identity: str = Field(default_factory=generate_identity)

    package: TaskPackage
    action: str
    cursor_key: str

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

    @field_validator("cursor_key", mode="before")
    @classmethod
    def validate_cursor_key(cls, value: object) -> str:
        text = str(value)
        if not text:
            raise ValueError("cursor_key must not be empty")
        return text

    @field_validator("claimed_at", mode="before")
    @classmethod
    def validate_claimed_at(cls, value: object) -> int | None:
        if value is None or value == "":
            return None
        return int(value)

    @field_serializer("created_at", "claimed_at")
    def serialize_optional_int(self, value: int | None) -> str:
        return "" if value is None else str(value)


class Committed(Task):
    """Successful task completion notice.

    The committed record is the source task copied under committed:<task_identity>.
    Its existence is the success signal. Routing should use cursor_key to recover
    the call/process identity instead of deriving process identity from this key.
    """

    kind: ClassVar[str] = "committed"

    task_identity: str
    task_key: str
    committed_at: int = Field(default_factory=timestamp)

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
        text = str(value)
        if not text:
            raise ValueError("task_key must not be empty")
        return text

    @field_serializer("committed_at")
    def serialize_committed_at(self, value: int) -> str:
        return str(value)


class Outcome(RedisMessage):
    """Completed task record copied forward with a result.

    Outcome reuses the source task identity so task:<id> and outcome:<id>
    are directly paired for forensics.
    """

    kind: ClassVar[str] = "outcome"

    identity: str
    task_identity: str

    package: TaskPackage
    action: str
    cursor_key: str
    result: OutcomeResult

    created_at: int
    claimed_at: int | None = None
    completed_at: int = Field(default_factory=timestamp)

    @classmethod
    def from_task(
        cls,
        task: Task,
        *,
        result: OutcomeResult,
    ) -> Self:
        return cls(
            identity=task.identity,
            task_identity=task.identity,
            package=task.package,
            action=task.action,
            cursor_key=task.cursor_key,
            result=result,
            created_at=task.created_at,
            claimed_at=task.claimed_at,
        )

    @field_validator("identity", "task_identity", mode="before")
    @classmethod
    def validate_identity_fields(cls, value: object) -> str:
        return redis_key_segment_text(value, "identity")

    @field_validator("action", mode="before")
    @classmethod
    def validate_action(cls, value: object) -> str:
        return redis_key_segment_text(value, "action")

    @field_validator("cursor_key", mode="before")
    @classmethod
    def validate_cursor_key(cls, value: object) -> str:
        text = str(value)
        if not text:
            raise ValueError("cursor_key must not be empty")
        return text

    @field_validator("claimed_at", mode="before")
    @classmethod
    def validate_claimed_at(cls, value: object) -> int | None:
        if value is None or value == "":
            return None
        return int(value)

    @field_serializer("created_at", "claimed_at", "completed_at")
    def serialize_optional_int(self, value: int | None) -> str:
        return "" if value is None else str(value)


__all__ = [
    "Committed",
    "Outcome",
    "OutcomeResult",
    "Task",
    "TaskPackage",
    "TaskStatus",
]
