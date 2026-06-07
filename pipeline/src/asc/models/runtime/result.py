from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar

from pydantic import ConfigDict, Field, field_validator

from asc.core.identity import generate_identity
from asc.models.helpers.plain import redis_key_segment_text
from asc.redis.model_base import RedisModel


class StepResultRecord(RedisModel):
    """Runtime record for one completed step attempt.

    Engine adapters are expected to return the canonical engine-result shape.
    This model does not try to normalize arbitrary provider payloads.
    """

    namespace: ClassVar[str] = "runtime"
    domain: ClassVar[str] = namespace
    kind: ClassVar[str] = "step-result"

    identity: str = Field(default_factory=generate_identity)
    model_config = ConfigDict(extra="ignore")

    call_identity: str
    step_number: int
    raw_json: Any
    content: str | None = None
    fail_message: str | None = None
    started_at: int | None = None
    completed_at: int | None = None
    input_key: str | None = None
    output_key: str | None = None
    handler: str | None = None
    engine: str | None = None
    prompt: str | None = None
    input_content: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None

    @field_validator("identity", "call_identity", mode="before")
    @classmethod
    def validate_redis_identity(cls, value: object) -> str:
        return redis_key_segment_text(value, "identity")

    @field_validator("step_number", mode="before")
    @classmethod
    def validate_positive_int(cls, value: object) -> int | None:
        if value is None:
            return None
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("integer fields must be integers")
        if value < 1:
            raise ValueError("integer fields must be greater than zero")
        return value

    @classmethod
    def from_engine_result(
        cls,
        *,
        call_identity: str,
        step_number: int,
        engine_result: Any,
        started_at: int | None = None,
        completed_at: int | None = None,
        **metadata: Any,
    ) -> "StepResultRecord":
        """Build a step result from a canonical engine-result object.

        Expected engine-result fields:

        - content: str | None
        - fail_message: str | None
        - record: Any | None

        The engine layer owns provider-specific normalization. If the object is
        not canonical, this constructor fails instead of guessing.
        """

        if isinstance(engine_result, Exception):
            return cls.from_exception(
                engine_result,
                call_identity=call_identity,
                step_number=step_number,
                started_at=started_at,
                completed_at=completed_at,
                **metadata,
            )

        content = _optional_str_field(engine_result, "content")
        fail_message = _optional_str_field(engine_result, "fail_message")
        raw_json = _raw_record(engine_result)

        if content is None and fail_message is None:
            raise ValueError(
                "canonical engine result must include content or fail_message"
            )

        if content is not None and fail_message is not None:
            raise ValueError(
                "canonical engine result cannot include both content and fail_message"
            )

        return cls(
            call_identity=call_identity,
            step_number=step_number,
            raw_json=raw_json,
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
        call_identity: str,
        step_number: int,
        started_at: int | None = None,
        completed_at: int | None = None,
        **metadata: Any,
    ) -> "StepResultRecord":
        return cls(
            call_identity=call_identity,
            step_number=step_number,
            raw_json={
                "exception_type": type(exc).__name__,
                "message": str(exc),
            },
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


def _optional_str_field(value: Any, name: str) -> str | None:
    field_value = _field(value, name)

    if field_value is None:
        return None

    if not isinstance(field_value, str):
        raise ValueError(f"canonical engine result field {name!r} must be a string")

    text = field_value.strip()
    return text or None


def _raw_record(engine_result: Any) -> Any:
    record = _field(engine_result, "record")
    if record is not None:
        return record

    if isinstance(engine_result, Mapping):
        return dict(engine_result)

    model_dump = getattr(engine_result, "model_dump", None)
    if callable(model_dump):
        try:
            return model_dump(mode="json")
        except TypeError:
            return model_dump()

    return {
        "type": type(engine_result).__name__,
        "repr": repr(engine_result),
    }


__all__ = ["StepResultRecord"]
