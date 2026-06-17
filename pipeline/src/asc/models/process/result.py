from __future__ import annotations

from typing import Any, Literal

from pydantic import ConfigDict, Field

from asc.core.timestamp import timestamp
from asc.redis.model_base import RedisModel


class Result(RedisModel):
    """Successful runtime payload for one worker-produced step result."""

    model_config = ConfigDict(extra="allow")

    kind: Literal["result"] = "result"

    content: str | None = None
    raw_json: Any = None

    started_at: int | None = None
    completed_at: int | None = None
    created_at: int = Field(default_factory=timestamp)

class Failure(RedisModel):
    """Failed runtime payload for one worker-produced step result."""

    model_config = ConfigDict(extra="allow")

    kind: Literal["failure"] = "failure"

    content: str | None = None
    failure_reason: str | None = None
    raw_json: Any = None

    started_at: int | None = None
    completed_at: int | None = None
    created_at: int = Field(default_factory=timestamp)

StepResult = Result
StepFailure = Failure

__all__ = ["Result", "Failure", "StepResult", "StepFailure"]