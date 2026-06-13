from __future__ import annotations

from typing import Any, Literal

from pydantic import ConfigDict, Field

from asc.core.timestamp import timestamp
from asc.redis.key import RedisKey
from asc.redis.model_base import RedisModel


class StepResultRecord(RedisModel):
    """Runtime payload for one worker-produced step result.

    The Redis key owns call identity and step number. The hash owns only the
    result payload. Engines return the constructor arguments for this model.
    """

    model_config = ConfigDict(extra="allow")

    type: Literal["runtime-step-result"] = "runtime-step-result"

    content: str | None = None
    fail_message: str | None = None
    raw_json: Any = None

    started_at: int | None = None
    completed_at: int | None = None
    created_at: int = Field(default_factory=timestamp)

    def save_as(self, key: str) -> None:
        RedisKey(key).hset(mapping=self.redis_hash())


__all__ = ["StepResultRecord"]
