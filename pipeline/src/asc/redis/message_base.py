from typing import TypeVar

from asc.redis.model_base import RedisRecord
from pydantic import field_validator


T = TypeVar("T", bound="RedisMessage")



class RedisMessage(RedisRecord):
    """Base for ephemeral Redis process messages.

    Messages are queue/control envelopes, not durable call-owned artifacts.
    Their keys are intentionally standalone:

        kind:identity

    Provenance belongs in hash fields such as cursor_key, call_key, plan_key,
    input_key, output_key, source_task_key, and task_number.
    """

    ttl_seconds: int | None = None

    def save(self, value=None) -> str:  # type: ignore[no-untyped-def]
        key = super().save(value)
        ttl = self.ttl_seconds
        if ttl is not None:
            if not isinstance(ttl, int) or ttl <= 0:
                raise ValueError(f"{self.__class__.__name__}.ttl_seconds must be a positive int or None")
            self.__class__.resolve_key(key).expire(ttl)
        return key
    
    @field_validator("ttl_seconds", "claimed_at", mode="before", check_fields=False)
    @classmethod
    def empty_optional_ints_are_none(cls, value):
        if value == "":
            return None
        return value
    
    

__all__ = ["RedisMessage"]
