"""Runtime job records.

Each daemon has its own model with hard-coded Redis domain/kind. These models
use RedisModel.save() and RedisModel.load(); they do not define key() or
redis_key() methods.
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import ConfigDict, field_serializer

from asc.redis.model_base import RedisModel


class _JobBase(RedisModel):
    domain: ClassVar[str] = "runtime"

    model_config = ConfigDict(extra="forbid")

    identity: str
    call_identity: str
    cursor_key: str
    action: str
    step_number: int = 0
    engine: str
    handler: str = ""
    input_model: str
    input_key: str
    output_model: str
    output_key: str
    args_json: str = "{}"

    @field_serializer("step_number")
    def _serialize_step_number(self, value: int) -> str:
        return str(value)


class WorkerJobRecord(_JobBase):
    kind: ClassVar[str] = "worker-job"


class LedgerJobRecord(_JobBase):
    kind: ClassVar[str] = "ledger-job"


# Backward-compatible aliases for older imports.
WorkerJob = WorkerJobRecord
ScrivenerJob = LedgerJobRecord
ScrivenerJobRecord = LedgerJobRecord


__all__ = [
    "LedgerJobRecord",
    "ScrivenerJob",
    "ScrivenerJobRecord",
    "WorkerJob",
    "WorkerJobRecord",
]
