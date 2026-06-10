from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import ConfigDict, Field, field_validator

from asc.core.timestamp import timestamp
from asc.models.helpers.plain import plain_non_empty_string, redis_key_segment_text
from asc.redis.model_base import RedisModel


class RuntimeContentRecord(RedisModel):
    """Runtime text payload.

    This model validates payload shape only. Orchestrator decides which runtime
    content slot is current for a call and saves/loads through RedisModel.
    """

    model_config = ConfigDict(extra="allow")

    domain: ClassVar[str] = "runtime"
    kind: ClassVar[str] = "content"

    type: Literal["runtime-content"] = "runtime-content"
    identity: str
    content: str
    origin: str = "runtime"
    produced_by_step: int | None = None
    created_at: int = Field(default_factory=timestamp)

    @field_validator("identity", mode="before")
    @classmethod
    def validate_identity(cls, value: object) -> str:
        return redis_key_segment_text(value, "identity")

    @field_validator("content", mode="before")
    @classmethod
    def validate_content(cls, value: object) -> str:
        return plain_non_empty_string(value, "content")

    @classmethod
    def from_source(cls, *, identity: str, content: str) -> "RuntimeContentRecord":
        return cls(identity=identity, content=content, origin="source")


ContentRecord = RuntimeContentRecord

__all__ = ["ContentRecord", "RuntimeContentRecord"]
