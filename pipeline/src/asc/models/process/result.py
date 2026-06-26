from __future__ import annotations

from typing import Any, ClassVar, Self

from pydantic import ConfigDict, Field, field_serializer, field_validator

from asc.core.timestamp import timestamp
from asc.models.helpers.plain import redis_key_segment_text
from asc.redis.key import RedisKey
from asc.redis.model_base import RedisModel


class Result(RedisModel):
    """Base class for successful worker output.

    Engines instantiate concrete result objects with only the payload produced
    by that engine. The worker executor owns runtime custody metadata and passes
    the Redis address at save time:

    - identity: source call identity
    - suffix: producing step number

    Successful worker results have three concrete Redis key kinds:

    - response: successful LLM completion
    - transform: successful script transform
    - retrieval: successful RAG/retrieval operation
    """

    model_config = ConfigDict(extra="allow")

    kind: ClassVar[str] = "result"

    content: str
    raw_json: Any = Field(default_factory=dict)
    created_at: int = Field(default_factory=timestamp)

    @classmethod
    def output_key_for(cls, *, identity: object, suffix: object) -> str:
        return str(
            RedisKey(
                kind=cls.kind,
                identity=_identity(identity),
                suffix=_step_suffix(suffix),
            )
        )

    def save(self, *, identity: object, suffix: object) -> str:  # type: ignore[override]
        output_key = self.output_key_for(identity=identity, suffix=suffix)
        super().save(output_key)
        return output_key

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
    """Base class for failed daemon/worker output.

    Failure records all use the Redis key kind ``failure``. The
    ``failure_type`` field distinguishes internal boundary errors from failed
    external calls. Failures carry content so the chain can continue when the
    orchestrator policy allows it.

    Worker step failures pass a step suffix at save time. Daemon/task failures
    may omit the suffix and are saved as two-segment failure:<task_identity>
    records.
    """

    model_config = ConfigDict(extra="allow")

    kind: ClassVar[str] = "failure"

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
        return str(
            RedisKey(
                kind=cls.kind,
                identity=_identity(identity),
                suffix=_optional_suffix(suffix),
            )
        )

    def save(self, *, identity: object, suffix: object | None = None) -> str:  # type: ignore[override]
        output_key = self.output_key_for(identity=identity, suffix=suffix)
        super().save(output_key)
        return output_key

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

        return cls(
            content=str(exc),
            failure_reason=type(exc).__name__,
            raw_json=raw_json,
            boundary=boundary,
        )


class ExternalFailure(Failure):
    """Failed external call, such as an LLM or retrieval provider rejection."""

    failure_type: str = "external"


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
    if value is None:
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
