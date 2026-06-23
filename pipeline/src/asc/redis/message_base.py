from typing import TypeVar

from pydantic import field_validator

from asc.redis.model_base import RedisModel
from asc.redis.primitives import keys


T = TypeVar("T", bound="RedisMessage")


class RedisMessage(RedisModel):
    """Base for ephemeral Redis process messages.

    Messages are queue/control envelopes. They use the normal RedisModel key
    policy: kind:identity unless the subclass explicitly defines a suffix.

    Provenance belongs in hash fields such as cursor_key, call_key, plan_key,
    input_key, output_key, source_task_key, and task_number.
    """

    ttl_seconds: int | None = None

    def save(self, key: str | object | None = None) -> str:  # type: ignore[override]
        raw_key = super().save(key)  # type: ignore[arg-type]
        ttl = self.ttl_seconds
        if ttl is not None:
            if not isinstance(ttl, int) or ttl <= 0:
                raise ValueError(
                    f"{self.__class__.__name__}.ttl_seconds must be "
                    "a positive int or None"
                )
            redis_key = self.__class__.redis_key_from_raw(raw_key)
            keys.expire(redis_key, ttl)
        return raw_key

    @field_validator("ttl_seconds", "claimed_at", mode="before", check_fields=False)
    @classmethod
    def empty_optional_ints_are_none(cls, value):
        if value == "":
            return None
        return value


__all__ = ["RedisMessage"]
