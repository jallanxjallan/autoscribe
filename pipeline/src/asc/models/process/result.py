from __future__ import annotations

from typing import Any, ClassVar

from pydantic import ConfigDict, Field

from asc.core.timestamp import timestamp
from asc.redis.model_base import RedisModel


class Result(RedisModel):
    """Successful payload for one worker-produced step result."""

    model_config = ConfigDict(extra="forbid")

    kind: ClassVar[str] = "result"
    suffix: ClassVar[str] = "step"

    content: str
    raw_json: Any
    started_at: int
    completed_at: int
    created_at: int = Field(default_factory=timestamp)


class Failure(RedisModel):
    """Failed payload for one worker-produced step result."""

    model_config = ConfigDict(extra="forbid")

    kind: ClassVar[str] = "failure"
    suffix: ClassVar[str] = "step"

    content: str
    failure_reason: str
    raw_json: Any
    started_at: int
    completed_at: int
    created_at: int = Field(default_factory=timestamp)


__all__ = ["Result", "Failure"]
