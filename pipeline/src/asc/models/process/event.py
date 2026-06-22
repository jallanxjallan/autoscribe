from typing import ClassVar

from pydantic import ConfigDict, Field, field_validator

from asc.core.timestamp import timestamp
from asc.models.helpers.plain import redis_key_segment_text
from asc.redis.model_base import RedisModel


class Committed(RedisModel):
    """Marker that a scrivener operation completed successfully.

    The identity is the producer ScrivenerTask identity.  Processing-chain
    details remain on the task; the committed record is only the operational
    notice payload.
    """

    model_config = ConfigDict(extra="forbid")

    kind: ClassVar[str] = "committed"

    identity: str
    created_at: int = Field(default_factory=timestamp)

    @field_validator("identity", mode="before")
    @classmethod
    def validate_identity(cls, value: object) -> str:
        return redis_key_segment_text(value, "identity")


__all__ = ["Committed"]
