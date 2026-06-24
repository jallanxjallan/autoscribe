from __future__ import annotations

from typing import Any, ClassVar, Self

from pydantic import ConfigDict, Field, field_serializer, field_validator

from asc.core.timestamp import timestamp
from asc.models.helpers.plain import redis_key_segment_text
from asc.redis.key import RedisKey
from asc.redis.model_base import RedisModel


class Result(RedisModel):
    """Base class for successful worker output.

    Successful worker results have three concrete Redis key kinds:

    - response: successful LLM completion
    - transform: successful script transform
    - retrieval: successful RAG/retrieval operation

    The output key identity is the source call identity. The suffix is the
    step number, so all results derived from a call can be scanned by identity
    and each result can be tied back to the producing step.
    """

    model_config = ConfigDict(extra="forbid")

    kind: ClassVar[str] = "result"

    identity: str
    task_key: str
    task_identity: str
    data_key: str
    step_key: str
    step_number: int
    executor: str
    action: str
    content: str
    raw_json: Any
    created_at: int = Field(default_factory=timestamp)

    @classmethod
    def from_worker_output(
        cls,
        output: object,
        *,
        task: Any,
        step: Any,
        task_key: str,
    ) -> Result | Failure:
        if isinstance(output, Failure):
            return output.with_worker_context(task=task, step=step, task_key=task_key)

        if isinstance(output, Result):
            return output.with_worker_context(task=task, step=step, task_key=task_key)

        result_class = result_class_for_step(step)
        payload = payload_from_output(output)
        return result_class(
            identity=RedisKey(task.data_key).identity,
            task_key=task_key,
            task_identity=task.identity,
            data_key=task.data_key,
            step_key=task.step_key,
            step_number=_step_number(step),
            executor=_step_executor(step),
            action=_step_action(step),
            content=payload["content"],
            raw_json=payload["raw_json"],
        )

    @property
    def output_key(self) -> str:
        return str(
            RedisKey(
                kind=self.kind,
                identity=self.identity,
                suffix=str(self.step_number),
            )
        )

    def save(self, key: object | None = None) -> str:  # type: ignore[override]
        output_key = self.output_key if key is None else str(key)
        super().save(output_key)
        return output_key

    def with_worker_context(self, *, task: Any, step: Any, task_key: str) -> Self:
        return self.model_copy(
            update={
                "identity": RedisKey(task.data_key).identity,
                "task_key": task_key,
                "task_identity": task.identity,
                "data_key": task.data_key,
                "step_key": task.step_key,
                "step_number": _step_number(step),
                "executor": _step_executor(step),
                "action": _step_action(step),
            }
        )

    @field_validator("identity", "task_identity", mode="before")
    @classmethod
    def validate_identity_fields(cls, value: object) -> str:
        return redis_key_segment_text(value, "identity")

    @field_validator("task_key", "data_key", "step_key", "executor", "action", mode="before")
    @classmethod
    def validate_text_fields(cls, value: object) -> str:
        text = "" if value is None else str(value).strip()
        if not text:
            raise ValueError("result text fields must not be empty")
        return text

    @field_validator("step_number", mode="before")
    @classmethod
    def validate_step_number(cls, value: object) -> int:
        number = int(value)
        if number < 1:
            raise ValueError(f"step_number must be >= 1: {number}")
        return number

    @field_serializer("created_at", "step_number")
    def serialize_int(self, value: int) -> str:
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
    """

    model_config = ConfigDict(extra="forbid")

    kind: ClassVar[str] = "failure"

    identity: str
    failure_type: str
    content: str
    failure_reason: str
    raw_json: Any
    task_key: str | None = None
    task_identity: str | None = None
    data_key: str | None = None
    step_key: str | None = None
    step_number: int | None = None
    executor: str | None = None
    action: str | None = None
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
            identity=RedisKey(task.data_key).identity,
            task_key=task_key,
            task_identity=task.identity,
            data_key=task.data_key,
            step_key=task.step_key,
            step_number=_step_number(step),
            executor=_step_executor(step),
            action=_step_action(step),
            content=content,
            failure_reason=failure_reason,
            raw_json=raw_json,
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

    @property
    def output_key(self) -> str:
        suffix = None if self.step_number is None else str(self.step_number)
        return str(RedisKey(kind=self.kind, identity=self.identity, suffix=suffix))

    def save(self, key: object | None = None) -> str:  # type: ignore[override]
        output_key = self.output_key if key is None else str(key)
        super().save(output_key)
        return output_key

    def with_worker_context(self, *, task: Any, step: Any, task_key: str) -> Self:
        return self.model_copy(
            update={
                "identity": RedisKey(task.data_key).identity,
                "task_key": task_key,
                "task_identity": task.identity,
                "data_key": task.data_key,
                "step_key": task.step_key,
                "step_number": _step_number(step),
                "executor": _step_executor(step),
                "action": _step_action(step),
            }
        )

    @field_validator("identity", mode="before")
    @classmethod
    def validate_identity(cls, value: object) -> str:
        return redis_key_segment_text(value, "identity")

    @field_validator("task_identity", mode="before")
    @classmethod
    def validate_optional_identity(cls, value: object) -> str | None:
        if value is None:
            return None
        return redis_key_segment_text(value, "task_identity")

    @field_validator(
        "failure_type",
        "content",
        "failure_reason",
        "task_key",
        "data_key",
        "step_key",
        "executor",
        "action",
        "boundary",
        mode="before",
    )
    @classmethod
    def validate_optional_text(cls, value: object) -> str | None:
        if value is None:
            return None
        return str(value).strip()

    @field_validator("step_number", mode="before")
    @classmethod
    def validate_optional_step_number(cls, value: object) -> int | None:
        if value in (None, ""):
            return None
        number = int(value)
        if number < 1:
            raise ValueError(f"step_number must be >= 1: {number}")
        return number

    @field_serializer("created_at")
    def serialize_created_at(self, value: int) -> str:
        return str(value)

    @field_serializer("step_number")
    def serialize_optional_step_number(self, value: int | None) -> str:
        return "" if value is None else str(value)


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
        data_key = context.get("data_key") or getattr(task, "data_key", None)
        identity = RedisKey(data_key).identity if data_key else RedisKey(task_key).identity

        raw_json = {
            "task_key": task_key,
            "task_identity": getattr(task, "identity", None),
            "data_key": data_key,
            "step_key": context.get("step_key") or getattr(task, "step_key", None),
            "table": context.get("table") or getattr(task, "table", None),
            "error": str(exc),
            "error_type": type(exc).__name__,
            "boundary": boundary,
        }
        raw_json.update({key: value for key, value in context.items() if key not in raw_json})

        return cls(
            identity=identity,
            task_key=task_key,
            task_identity=getattr(task, "identity", None),
            data_key=data_key,
            step_key=raw_json.get("step_key"),
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


def result_class_for_step(step: Any) -> type[Result]:
    executor = _step_executor(step).lower()
    if executor in {"script", "transform"}:
        return Transform
    if executor in {"rag", "retrieval"}:
        return Retrieval
    return Response


def payload_from_output(output: object) -> dict[str, Any]:
    if isinstance(output, str):
        return {"content": output, "raw_json": output}

    if isinstance(output, dict):
        content = output.get("content") or output.get("text") or output.get("message") or ""
        return {"content": str(content), "raw_json": output}

    content = getattr(output, "content", None)
    if content is not None:
        raw_json = getattr(output, "raw_json", None)
        if raw_json is None:
            dump = getattr(output, "model_dump", None)
            raw_json = dump(mode="json") if callable(dump) else output
        return {"content": str(content), "raw_json": raw_json}

    return {"content": str(output), "raw_json": output}


def _step_number(step: Any) -> int:
    value = getattr(step, "step_number", None)
    if value is None:
        value = getattr(step, "number")
    number = int(value)
    if number < 1:
        raise ValueError(f"step_number must be >= 1: {number}")
    return number


def _step_executor(step: Any) -> str:
    value = getattr(step, "executor", None)
    if value in (None, ""):
        value = getattr(step, "engine", None)
    text = "" if value is None else str(value).strip()
    if not text:
        raise ValueError("step executor must not be empty")
    return text


def _step_action(step: Any) -> str:
    value = getattr(step, "action", None)
    if value in (None, ""):
        value = _step_executor(step)
    text = "" if value is None else str(value).strip()
    if not text:
        raise ValueError("step action must not be empty")
    return text


__all__ = [
    "Committed",
    "ExternalFailure",
    "Failure",
    "InternalFailure",
    "Response",
    "Result",
    "Retrieval",
    "Transform",
    "payload_from_output",
    "result_class_for_step",
]
