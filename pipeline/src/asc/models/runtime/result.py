from __future__ import annotations

from typing import Any, Literal

from pydantic import ConfigDict, Field

from asc.core.timestamp import timestamp
from asc.redis.model_base import RedisModel


class StepResult(RedisModel):
    """Successful runtime payload for one worker-produced step result."""

    model_config = ConfigDict(extra="allow")

    type: Literal["runtime-step-result"] = "runtime-step-result"

    content: str | None = None
    raw_json: Any = None

    started_at: int | None = None
    completed_at: int | None = None
    created_at: int = Field(default_factory=timestamp)

class StepFailure(RedisModel):
    """Failed runtime payload for one worker-produced step result."""

    model_config = ConfigDict(extra="allow")

    type: Literal["runtime-step-failure"] = "runtime-step-failure"

    content: str | None = None
    failure_reason: str | None = None
    raw_json: Any = None

    started_at: int | None = None
    completed_at: int | None = None
    created_at: int = Field(default_factory=timestamp)

__all__ = ["StepResult", "StepFailure"]