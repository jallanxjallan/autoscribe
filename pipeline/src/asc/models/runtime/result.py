from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar, Literal

from pydantic import ConfigDict, Field, field_validator

from asc.core.timestamp import timestamp
from asc.models.helpers.plain import positive_int, redis_key_segment_text
from asc.redis.model_base import RedisModel


class StepResultRecord(RedisModel):
    """Runtime result for one completed step attempt."""

    model_config = ConfigDict(extra="allow")

    domain: ClassVar[str] = "runtime"
    kind: ClassVar[str] = "step-result"

    type: Literal["runtime-step-result"] = "runtime-step-result"
    identity: str
    step_number: int
    raw_json: Any
    content: str | None = None
    fail_message: str | None = None
    started_at: int | None = None
    completed_at: int | None = None
    created_at: int = Field(default_factory=timestamp)

    @field_validator("identity", mode="before")
    @classmethod
    def validate_identity(cls, value: object) -> str:
        return redis_key_segment_text(value, "identity")

    @field_validator("step_number", mode="before")
    @classmethod
    def validate_step_number(cls, value: object) -> int:
        return positive_int(value, "step_number")

    @classmethod
    def from_engine_result(
        cls,
        *,
        identity: str,
        step_number: int,
        engine_result: Any,
        started_at: int | None = None,
        completed_at: int | None = None,
        **metadata: Any,
    ) -> "StepResultRecord":
        if isinstance(engine_result, Exception):
            return cls.from_exception(
                engine_result,
                identity=identity,
                step_number=step_number,
                started_at=started_at,
                completed_at=completed_at,
                **metadata,
            )

        content = _field(engine_result, "content")
        fail_message = _field(engine_result, "fail_message")
        if content is not None and not isinstance(content, str):
            raise ValueError("engine result content must be a string or None")
        if fail_message is not None and not isinstance(fail_message, str):
            raise ValueError("engine result fail_message must be a string or None")
        if content is None and fail_message is None:
            raise ValueError("engine result must include content or fail_message")

        return cls(
            identity=identity,
            step_number=step_number,
            raw_json=_raw_record(engine_result),
            content=content,
            fail_message=fail_message,
            started_at=started_at,
            completed_at=completed_at,
            **metadata,
        )

    @classmethod
    def from_exception(
        cls,
        exc: Exception,
        *,
        identity: str,
        step_number: int,
        started_at: int | None = None,
        completed_at: int | None = None,
        **metadata: Any,
    ) -> "StepResultRecord":
        return cls(
            identity=identity,
            step_number=step_number,
            raw_json={"exception_type": type(exc).__name__, "message": str(exc)},
            content=None,
            fail_message=str(exc),
            started_at=started_at,
            completed_at=completed_at,
            **metadata,
        )


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _raw_record(engine_result: Any) -> Any:
    record = _field(engine_result, "record")
    if record is not None:
        return record
    if isinstance(engine_result, Mapping):
        return dict(engine_result)
    model_dump = getattr(engine_result, "model_dump", None)
    if callable(model_dump):
        return model_dump()
    return {"type": type(engine_result).__name__, "repr": repr(engine_result)}


__all__ = ["StepResultRecord"]
