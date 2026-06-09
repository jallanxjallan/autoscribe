from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar

from pydantic import ConfigDict, field_validator, model_validator

from asc.models.helpers.plain import positive_int, redis_key_segment_text
from asc.redis.key import RedisKey
from asc.redis.model_base import RedisModel


class StepResultRecord(RedisModel):
    """Runtime record for one completed step attempt."""

    namespace: ClassVar[str] = "runtime"
    domain: ClassVar[str] = namespace
    kind: ClassVar[str] = "step-result"

    model_config = ConfigDict(extra="allow")

    identity: str | None = None
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

    @model_validator(mode="before")
    @classmethod
    def normalize_call_identity(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        if data.get("call_identity") is None and data.get("identity") is not None:
            data["call_identity"] = data["identity"]
        if data.get("identity") is None and data.get("call_identity") is not None:
            data["identity"] = data["call_identity"]
        return data

    @field_validator("identity", "call_identity", mode="before")
    @classmethod
    def validate_redis_identity(cls, value: object) -> str:
        return redis_key_segment_text(value, "identity")

    @field_validator("step_number", mode="before")
    @classmethod
    def validate_step_number(cls, value: object) -> int:
        return positive_int(value, "step_number")

    @classmethod
    def key_for_step(cls, call_identity: str, step_number: int) -> RedisKey:
        return RedisKey.from_parts(cls.domain, redis_key_segment_text(call_identity, "call_identity"), f"{cls.kind}.{positive_int(step_number, 'step_number')}")

    @classmethod
    def key_for_identity(cls, identity: str) -> RedisKey:
        raise TypeError("StepResultRecord requires step_number; use key_for_step(call_identity, step_number)")

    @property
    def redis_key(self) -> RedisKey:
        return self.key_for_step(self.call_identity, self.step_number)

    @classmethod
    def load(cls, call_identity: str, step_number: int, *, require: bool = True) -> "StepResultRecord | None":
        key = cls.key_for_step(call_identity, step_number)
        raw = key.get()
        if raw is None:
            if require:
                raise RuntimeError(f"Redis JSON record missing: {key}")
            return None
        return cls.model_validate_json(raw)

    @classmethod
    def load_from_key(cls, full_key: str | RedisKey, *, require: bool = True) -> "StepResultRecord | None":
        key = full_key if isinstance(full_key, RedisKey) else RedisKey(str(full_key))
        raw = key.get()
        if raw is None:
            if require:
                raise RuntimeError(f"Redis JSON record missing: {key}")
            return None
        return cls.model_validate_json(raw)

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
        if isinstance(engine_result, Exception):
            return cls.from_exception(engine_result, call_identity=call_identity, step_number=step_number, started_at=started_at, completed_at=completed_at, **metadata)

        content = _field(engine_result, "content")
        fail_message = _field(engine_result, "fail_message")
        if content is not None and not isinstance(content, str):
            raise ValueError("engine result content must be a string or None")
        if fail_message is not None and not isinstance(fail_message, str):
            raise ValueError("engine result fail_message must be a string or None")
        if content is None and fail_message is None:
            raise ValueError("engine result must include content or fail_message")

        return cls(
            call_identity=call_identity,
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
        call_identity: str,
        step_number: int,
        started_at: int | None = None,
        completed_at: int | None = None,
        **metadata: Any,
    ) -> "StepResultRecord":
        return cls(
            call_identity=call_identity,
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
