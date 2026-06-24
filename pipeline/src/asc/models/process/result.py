from __future__ import annotations

from typing import Any, ClassVar, Self

from pydantic import ConfigDict, Field, field_serializer, field_validator

from asc.core.timestamp import timestamp
from asc.models.helpers.plain import redis_key_segment_text
from asc.redis.model_base import RedisModel


class Response(RedisModel):
    """Successful worker output payload.

    The identity is the producer WorkerTask identity.  Routing/process-chain
    details remain on the task; the response contains only worker output.
    """

    model_config = ConfigDict(extra="forbid")

    kind: ClassVar[str] = "response"

    identity: str
    content: str
    raw_json: Any
    created_at: int = Field(default_factory=timestamp)

    @field_validator("identity", mode="before")
    @classmethod
    def validate_identity(cls, value: object) -> str:
        return redis_key_segment_text(value, "identity")


class Failure(RedisModel):
    """Failed worker output payload.

    The identity is the producer WorkerTask identity.  Routing/process-chain
    details remain on the task; the failure contains only failure details.
    """

    model_config = ConfigDict(extra="forbid")

    kind: ClassVar[str] = "failure"

    identity: str
    content: str
    failure_reason: str
    raw_json: Any
    created_at: int = Field(default_factory=timestamp)

    @field_validator("identity", mode="before")
    @classmethod
    def validate_identity(cls, value: object) -> str:
        return redis_key_segment_text(value, "identity")


class Committed(RedisModel):
    """Successful daemon task result.

    A committed record copies the concrete task payload under
    committed:<task_identity>. Its existence is the success signal.
    """

    model_config = ConfigDict(extra="allow")

    kind: ClassVar[str] = "committed"

    identity: str
    task_identity: str
    task_key: str
    committed_at: int = Field(default_factory=timestamp)

    @classmethod
    def from_task(cls, task: Any, *, task_key: str) -> Self:
        return cls.model_validate(
            {
                **task.model_dump(mode="json"),
                "identity": task.identity,
                "task_identity": task.identity,
                "task_key": task_key,
            }
        )

    @field_validator("identity", "task_identity", mode="before")
    @classmethod
    def validate_identity_fields(cls, value: object) -> str:
        return redis_key_segment_text(value, "identity")

    @field_validator("task_key", mode="before")
    @classmethod
    def validate_task_key(cls, value: object) -> str:
        text = "" if value is None else str(value).strip()
        if not text:
            raise ValueError("task_key must not be empty")
        return text

    @field_serializer("committed_at")
    def serialize_committed_at(self, value: int) -> str:
        return str(value)


__all__ = ["Committed", "Response", "Failure"]
