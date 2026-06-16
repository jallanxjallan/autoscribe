from __future__ import annotations

from typing import Any

from pydantic import Field

from asc.models.runtime.model_base import RedisModel


class ScrivenerResult(RedisModel):
    """Successful scrivener ledger write outcome.

    This mirrors worker StepResult at the daemon boundary: the daemon executes
    one job, persists an outcome artifact, and returns the cursor to the
    orchestrator. Policy remains outside scrivener.
    """

    type: str = "scrivener_result"
    identity: str
    action: str
    job_key: str = ""
    ledger_table: str = ""
    message: str = "completed"
    created_at: int | None = None

    @property
    def redis_key(self) -> str:
        return f"runtime:{self.identity}:scrivener.{self.action}.result"


class ScrivenerFailure(RedisModel):
    """Failed scrivener ledger write outcome.

    SQLite integrity errors, malformed engine output, bad export payloads, and
    other ledger-write problems all become data. The orchestrator decides what
    to do next.
    """

    type: str = "scrivener_failure"
    identity: str
    action: str
    job_key: str = ""
    ledger_table: str = ""
    fail_message: str
    failure_reason: str = ""
    raw_error_json: dict[str, Any] = Field(default_factory=dict)
    created_at: int | None = None

    @property
    def redis_key(self) -> str:
        return f"runtime:{self.identity}:scrivener.{self.action}.failure"


__all__ = ["ScrivenerFailure", "ScrivenerResult"]
