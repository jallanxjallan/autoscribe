from typing import Any, ClassVar

from pydantic import ConfigDict, Field, field_validator

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


__all__ = ["Response", "Failure"]
