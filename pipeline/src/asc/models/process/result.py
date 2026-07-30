from __future__ import annotations

from pathlib import Path
import traceback
from typing import Any, ClassVar, Self

from pydantic import (
    AliasChoices,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
)

from asc.core.identity import generate_identity
from asc.core.timestamp import timestamp
from asc.models.helpers.plain import redis_key_segment_text
from asc.redis.key import RedisKey
from asc.redis.message_base import RedisMessage
from asc.redis.model_base import RedisModel


class Result(RedisModel):
    """Base class for self-addressed successful worker output."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    kind: ClassVar[str] = "result"

    identity: str
    ordinal: int = Field(
        validation_alias=AliasChoices("ordinal", "suffix", "result_suffix", "step_number")
    )
    content: str
    raw_json: Any = Field(default_factory=dict)
    created_at: int = Field(default_factory=timestamp)

    @classmethod
    def output_key_for(
        cls,
        *,
        identity: object,
        ordinal: object | None = None,
        suffix: object | None = None,
    ) -> str:
        return RedisKey(
            kind=cls.kind,
            identity=_identity(identity),
            suffix=_required_ordinal(_coalesced_ordinal(ordinal=ordinal, suffix=suffix)),
        ).raw_key

    @property
    def result_suffix(self) -> str:
        """Compatibility alias while older result consumers are migrated."""
        return str(self.ordinal)

    @field_validator("identity", mode="before")
    @classmethod
    def validate_identity(cls, value: object) -> str:
        return _identity(value)

    @field_validator("ordinal", mode="before")
    @classmethod
    def validate_ordinal(cls, value: object) -> int:
        return _required_ordinal(value)

    @field_validator("content", mode="before")
    @classmethod
    def validate_content(cls, value: object) -> str:
        return "" if value is None else str(value)

    @field_serializer("created_at", "ordinal")
    def serialize_ints(self, value: int) -> str:
        return str(value)


class Response(Result):
    kind: ClassVar[str] = "response"


class Transform(Result):
    kind: ClassVar[str] = "transform"


class Retrieval(Result):
    kind: ClassVar[str] = "retrieval"


class Failure(RedisModel):
    """Base class for self-addressed failed daemon/worker output."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    kind: ClassVar[str] = "failure"

    identity: str
    ordinal: int | None = Field(
        default=None,
        validation_alias=AliasChoices("ordinal", "suffix", "result_suffix", "step_number"),
    )
    failure_type: str
    content: str
    failure_reason: str
    raw_json: Any = Field(default_factory=dict)
    boundary: str | None = None
    stage: str | None = None
    location: str | None = None
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
        ordinal = _step_ordinal(step)
        return ExternalFailure(
            identity=RedisKey(getattr(task, "data_key")).identity,
            ordinal=ordinal,
            content=content,
            failure_reason=failure_reason,
            raw_json={
                "task_key": task_key,
                "task_identity": getattr(task, "identity", None),
                "data_key": getattr(task, "data_key", None),
                "step_key": getattr(task, "step_key", None),
                "ordinal": ordinal,
                "step_number": ordinal,
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
    def output_key_for(
        cls,
        *,
        identity: object,
        ordinal: object | None = None,
        suffix: object | None = None,
    ) -> str:
        supplied_ordinal = _coalesced_ordinal(ordinal=ordinal, suffix=suffix)

        if supplied_ordinal is None and cls.component is not None:
            return RedisKey.from_parts(cls.kind, _identity(identity), cls.component).raw_key

        return RedisKey(
            kind=cls.kind,
            identity=_identity(identity),
            suffix=_required_ordinal(supplied_ordinal),
        ).raw_key

    @property
    def result_suffix(self) -> str | None:
        """Compatibility alias while older failure consumers are migrated."""
        return None if self.ordinal is None else str(self.ordinal)

    @field_validator("identity", mode="before")
    @classmethod
    def validate_identity(cls, value: object) -> str:
        return _identity(value)

    @field_validator("ordinal", mode="before")
    @classmethod
    def validate_ordinal(cls, value: object | None) -> int | None:
        if value in (None, ""):
            return None
        return _required_ordinal(value)

    @field_validator("failure_type", "content", "failure_reason", "boundary", mode="before")
    @classmethod
    def validate_optional_text(cls, value: object) -> str | None:
        if value is None:
            return None
        return str(value).strip()

    @field_serializer("created_at")
    def serialize_created_at(self, value: int) -> str:
        return str(value)

    @field_serializer("ordinal")
    def serialize_ordinal(self, value: int | None) -> str:
        return "" if value is None else str(value)


class InternalFailure(Failure):
    component: ClassVar[str] = "internal"

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

        return cls(
            identity=identity,
            content=str(exc),
            failure_reason=type(exc).__name__,
            raw_json=raw_json,
            boundary=boundary,
        )


class ExternalFailure(Failure):
    failure_type: str = "external"


class ProcessFailure(Failure):
    """Unique failure event emitted by a non-engine pipeline stage."""

    component: ClassVar[str] = "record"

    identity: str = Field(default_factory=generate_identity)
    failure_type: str = "internal"
    stage: str
    location: str
    process_identity: str | None = None


def failure_location(exc: BaseException) -> str:
    """Return the deepest raising file/module and function without a traceback."""

    frames = traceback.extract_tb(exc.__traceback__) if exc.__traceback__ else []
    frame = frames[-1] if frames else None
    if frame is None:
        return f"{type(exc).__module__}.{type(exc).__qualname__}"

    path = Path(frame.filename)
    parts = list(path.with_suffix("").parts)
    try:
        start = len(parts) - 1 - parts[::-1].index("asc")
        module = ".".join(parts[start:])
    except ValueError:
        module = path.stem

    return f"{module}.{frame.name}"


def record_failure(
    *,
    stage: str,
    exc: BaseException,
    process_identity: str | None = None,
    **context: Any,
) -> str:
    """Persist one unique failure key for a pipeline-stage exception."""

    location = failure_location(exc)
    raw_json = {
        "stage": stage,
        "location": location,
        "process_identity": process_identity,
        "error": str(exc),
        "error_type": type(exc).__name__,
        **context,
    }
    failure = ProcessFailure(
        stage=stage,
        location=location,
        process_identity=process_identity,
        content=str(exc),
        failure_reason=type(exc).__name__,
        boundary=stage,
        raw_json=raw_json,
    )
    return failure.save()


class Committed(RedisMessage):
    """Transient scrivener completion message, not a persisted Redis hash model."""

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


def _coalesced_ordinal(*, ordinal: object | None, suffix: object | None) -> object | None:
    if ordinal not in (None, "") and suffix not in (None, ""):
        raise ValueError("pass either ordinal or suffix, not both")
    return ordinal if ordinal not in (None, "") else suffix


def _required_ordinal(value: object) -> int:
    text = "" if value is None else str(value).strip()
    if not text:
        raise ValueError("ordinal must not be empty")

    number = int(text)
    if number < 1:
        raise ValueError(f"ordinal must be >= 1: {number}")

    return number


def _step_ordinal(step: Any) -> int:
    value = getattr(step, "ordinal", None)
    if value in (None, ""):
        value = getattr(step, "step_number", None)
    return _required_ordinal(value)


__all__ = [
    "Committed",
    "ExternalFailure",
    "Failure",
    "InternalFailure",
    "ProcessFailure",
    "Response",
    "Result",
    "Retrieval",
    "Transform",
    "failure_location",
    "record_failure",
]
