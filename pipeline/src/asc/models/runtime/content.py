from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from asc.models.helpers.plain import plain_non_empty_string, positive_int, redis_key_segment_text
from asc.redis.key import RedisKey
from asc.redis.model_base import RedisModel


def runtime_content_key(*, domain: str, identity: str, position: int) -> str:
    return f"{redis_key_segment_text(domain, 'domain')}:{redis_key_segment_text(identity, 'identity')}:content.{positive_int(position, 'position')}"


class RuntimeContentRef(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: Literal["runtime-content-ref"] = "runtime-content-ref"
    record_type: Literal["runtime-content"] = "runtime-content"
    identity: str
    position: int = Field(ge=1)


class RuntimeContentRecord(RedisModel):
    domain: ClassVar[str] = "runtime"
    kind: ClassVar[str] = "content"

    model_config = ConfigDict(extra="allow")

    identity: str
    position: int
    origin: str
    produced_by_step: int | None = None
    content: str

    @field_validator("identity", mode="before")
    @classmethod
    def validate_identity(cls, value: object) -> str:
        return redis_key_segment_text(value, "identity")

    @field_validator("position", mode="before")
    @classmethod
    def validate_position(cls, value: object) -> int:
        return positive_int(value, "position")

    @field_validator("produced_by_step", mode="before")
    @classmethod
    def validate_produced_by_step(cls, value: object) -> int | None:
        if value is None:
            return None
        return positive_int(value, "produced_by_step")

    @field_validator("content", mode="before")
    @classmethod
    def validate_content(cls, value: object) -> str:
        return plain_non_empty_string(value, "content")

    @classmethod
    def from_source(cls, *, identity: str, content: str) -> "RuntimeContentRecord":
        return cls(identity=identity, position=1, origin="source", produced_by_step=None, content=content)

    @classmethod
    def key_for_position(cls, *, identity: str, position: int, domain: str | None = None) -> str:
        return runtime_content_key(domain=domain or cls.domain, identity=identity, position=position)

    @classmethod
    def key_for_step_result(cls, *, identity: str, step_number: int, domain: str | None = None) -> str:
        return cls.key_for_position(domain=domain, identity=identity, position=positive_int(step_number, "step_number") + 1)

    @property
    def redis_key(self) -> RedisKey:
        return RedisKey(self.key_for_position(domain=self.domain, identity=self.identity, position=self.position))

    def to_ref(self) -> RuntimeContentRef:
        return RuntimeContentRef(identity=self.identity, position=self.position)

    @classmethod
    def load(cls, identity: str, position: int, *, require: bool = True) -> "RuntimeContentRecord | None":
        key = RedisKey(cls.key_for_position(identity=identity, position=position))
        raw = key.get()
        if raw is None:
            if require:
                raise RuntimeError(f"Redis JSON record missing: {key}")
            return None
        return cls.model_validate_json(raw)

    @classmethod
    def load_from_key(cls, full_key: str | RedisKey, *, require: bool = True) -> "RuntimeContentRecord | None":
        key = full_key if isinstance(full_key, RedisKey) else RedisKey(str(full_key))
        raw = key.get()
        if raw is None:
            if require:
                raise RuntimeError(f"Redis JSON record missing: {key}")
            return None
        return cls.model_validate_json(raw)


__all__ = ["RuntimeContentRecord", "RuntimeContentRef", "runtime_content_key"]
