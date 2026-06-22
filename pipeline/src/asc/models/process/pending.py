"""Short-lived marker for worker tasks in progress.

A results slot may store this model's Redis key after the orchestrator assigns a
worker task and before the worker returns a response or failure.  The identity is
the producer WorkerTask identity; processing-chain details remain on that task.
"""


from typing import ClassVar, Literal

from pydantic import ConfigDict, Field, field_serializer, field_validator

from asc.core.timestamp import timestamp
from asc.models.helpers.plain import redis_key_segment_text
from asc.redis.model_base import RedisModel


DEFAULT_PENDING_TTL_SECONDS = 60 * 60


class Pending(RedisModel):
    """Short-lived marker for a worker-owned operation."""

    model_config = ConfigDict(extra="forbid")

    kind: ClassVar[str] = "pending"
    default_ttl_seconds: ClassVar[int] = DEFAULT_PENDING_TTL_SECONDS

    type: Literal["pending"] = "pending"

    identity: str
    created_at: int = Field(default_factory=timestamp)

    @field_validator("identity", mode="before")
    @classmethod
    def validate_identity(cls, value: object) -> str:
        return redis_key_segment_text(value, "identity")

    @field_serializer("created_at")
    def serialize_created_at(self, value: int) -> str:
        return str(value)


__all__ = ["DEFAULT_PENDING_TTL_SECONDS", "Pending"]
