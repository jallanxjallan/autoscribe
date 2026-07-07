from __future__ import annotations

from typing import Any, ClassVar, Self

from pydantic import ConfigDict, Field, field_serializer, field_validator

from asc.core.timestamp import timestamp
from asc.models.helpers.plain import redis_key_segment_text
from asc.redis.key import RedisKey
from asc.redis.model_base import RedisModel


class Result(RedisModel):
    """Base class for successful worker output.

    Engines return instantiated, self-addressed result models. The worker may
    validate custody coordinates, then materializes the artifact by calling
    ``save()``. Redis keys are deterministic:

        response:<call_identity>:<step_number>
        transform:<call_identity>:<step_number>
        retrieval:<call_identity>:<step_number>
    """

    model_config = ConfigDict(extra="allow")

    kind: ClassVar[str] = "result"

    identity: str
    suffix: str
    content: str
    raw_json: Any = Field(default_factory=dict)
    created_at: int = Field(default_factory=timestamp)

    @classmethod
    def output_key_for(cls, *, identity: object, suffix: object) -> str:
        return RedisKey(
            kind=cls.kind,
            identity=_identity(identity),
            suffix=_step_suffix(suffix),
        ).raw_key

    @property
    def redis_key(self) -> RedisKey:
        return RedisKey(
            kind=self.kind,
            identity=_identity(self.identity),
            suffix=_step_suffix(self.suffix),
        )

    @property
    def raw_key(self) -> str:
        return self.redis_key.raw_key

    def save(self) -> str:  # type: ignore[override]
        return super().save(self.redis_key)

    @field_validator("identity", mode="before")
    @classmethod
    def validate_identity(cls, value: object) -> str:
        return _identity(value)

    @field_validator("suffix", mode="before")
    @classmethod
    def validate_suffix(cls, value: object) -> str:
        return _step_suffix(value)

    @field_validator("content", mode="before")
    @classmethod
    def validate_content(cls, value: object) -> str:
        return "" if value is None else str(value)

    @field_serializer("created_at")
    def serialize_created_at(self, value: int) -> str:
        return str(value)


class Response(Result):
    """Successful LLM call completion."""

    kind: ClassVar[str] = "response"


class Transform(Result):
    """Successful script transform."""

    kind: ClassVar[str] = "transform"


class Retrieval(Result):
    """Successful RAG/retrieval operation."""

    kind: ClassVar[str] = "retrieval"


class Failure(RedisModel):
    """Failed daemon, worker, or external call output.

    Worker-step failures are self-addressed with the source call identity and
    producing step suffix:

        failure:<call_identity>:<step_number>

    Daemon/task failures may omit suffix and are addressed as:

        failure:<task_identity>
    """

    model_config = ConfigDict(extra="allow")

    kind: ClassVar[str] = "failure"

    identity: str
    suffix: str | None = None
    failure_type: str
    content: str
    failure_reason: str
    raw_json: Any = Field(default_factory=dict)
    boundary: str | None = None
    created_at: int = Field(default_factory=timestamp)

    @classmethod
    def internal(
        cls,
        *,
        task_key: str,
        task: Any | None,
        exc: Exception,
        boundary: str,
        **context: Any,
    ) -> InternalFailure:
        return InternalFailure.from_exception(
            task_key=task_key,
            task=task,
            exc=exc,
            boundary=boundary,
            **context,
        )

    @classmethod
    def external(
        cls,
        *,
        task_key: str,
        task: Any,
        step: Any,
        content: str,
        failure_reason: str,
        raw_json: Any,
    ) -> ExternalFailure:
        return ExternalFailure(
            identity=RedisKey(getattr(task, "data_key")).identity,
            suffix=getattr(step, "step_number"),
            content=content,
            failure_reason=failure_reason,
            raw_json={
                "task_key": task_key,
                "task_identity": getattr(task, "identity", None),
                "data_key": getattr(task, "data_key", None),
                "step_key": getattr(task, "step_key", None),
                "step_number": getattr(step, "step_number", None),
                "executor": getattr(step, "executor", None) or getattr(step, "engine", None),
                "action": getattr(step, "action", None),
                "provider": raw_json,
            },
        )

    @classmethod
    def from_exception(
        cls,
        *,
        task_key: str,
        task: Any | None,
        exc: Exception,
        boundary: str,
        **context: Any,
    ) -> InternalFailure:
        return InternalFailure.from_exception(
            task_key=task_key,
            task=task,
            exc=exc,
            boundary=boundary,
            **context,
        )

    @classmethod
    def output_key_for(cls, *, identity: object, suffix: object | None = None) -> str:
        return RedisKey(
            kind=cls.kind,
            identity=_identity(identity),
            suffix=_optional_suffix(suffix),
        ).raw_key

    @property
    def redis_key(self) -> RedisKey:
        return RedisKey(
            kind=self.kind,
            identity=_identity(self.identity),
            suffix=_optional_suffix(self.suffix),
        )

    @property
    def raw_key(self) -> str:
        return self.redis_key.raw_key

    def save(self) -> str:  # type: ignore[override]
        return super().save(self.redis_key)

    @field_validator("identity", mode="before")
    @classmethod
    def validate_identity(cls, value: object) -> str:
        return _identity(value)

    @field_validator("suffix", mode="before")
    @classmethod
    def validate_failure_suffix(cls, value: object | None) -> str | None:
        return _optional_suffix(value)

    @field_validator("failure_type", "content", "failure_reason", "boundary", mode="before")
    @classmethod
    def validate_optional_text(cls, value: object) -> str | None:
        if value is None:
            return None
        return str(value).strip()

    @field_serializer("created_at")
    def serialize_created_at(self, value: int) -> str:
        return str(value)


class InternalFailure(Failure):
    """Internal daemon or executor boundary failure."""

    failure_type: str = "internal"

    @classmethod
    def from_exception(
        cls,
        *,
        task_key: str,
        task: Any | None,
        exc: Exception,
        boundary: str,
        **context: Any,
    ) -> Self:
        raw_json = {
            "task_key": task_key,
            "task_identity": getattr(task, "identity", None),
            "data_key": context.get("data_key") or getattr(task, "data_key", None),
            "step_key": context.get("step_key") or getattr(task, "step_key", None),
            "table": context.get("table") or getattr(task, "table", None),
            "error": str(exc),
            "error_type": type(exc).__name__,
            "boundary": boundary,
        }
        raw_json.update({key: value for key, value in context.items() if key not in raw_json})

        identity = context.get("identity") or getattr(task, "identity", None)
        if not identity:
            identity = RedisKey(task_key).identity

        suffix = context.get("suffix")

        return cls(
            identity=identity,
            suffix=suffix,
            content=str(exc),
            failure_reason=type(exc).__name__,
            raw_json=raw_json,
            boundary=boundary,
        )


class ExternalFailure(Failure):
    """Failed external call, such as an LLM or retrieval provider rejection."""

    failure_type: str = "external"


class Committed(RedisModel):
    """Successful daemon task result."""

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


def _identity(value: object) -> str:
    return redis_key_segment_text(value, "identity")


def _step_suffix(value: object) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        raise ValueError("result suffix must not be empty")

    number = int(text)
    if number < 1:
        raise ValueError(f"result suffix must be >= 1: {number}")

    return str(number)


def _optional_suffix(value: object | None) -> str | None:
    if value in (None, ""):
        return None
    return _step_suffix(value)


__all__ = [
    "Committed",
    "ExternalFailure",
    "Failure",
    "InternalFailure",
    "Response",
    "Result",
    "Retrieval",
    "Transform",
]
