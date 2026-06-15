from __future__ import annotations

import json
from typing import Any, ClassVar, Literal

from pydantic import Field, field_serializer

from asc.redis.model_base import RedisModel


class RuntimeJobBase(RedisModel):
    """
    Base model for daemon-specific runtime jobs.

    Subclasses hard-code domain/kind so callers only pass call_identity.
    """

    domain: ClassVar[str]
    kind: ClassVar[str]

    call_identity: str
    step_number: int

    engine: str
    script: str | None = None

    input_model: str
    input_key: str

    output_model: str
    output_key: str

    args: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def redis_key(cls, call_identity: str) -> str:
        return f"{cls.domain}:{call_identity}:{cls.kind}"

    @property
    def key(self) -> str:
        return self.redis_key(self.call_identity)

    @field_serializer("args")
    def serialize_args(self, value: dict[str, Any]) -> str:
        return json.dumps(value, ensure_ascii=False)

    @classmethod
    def from_redis_hash(cls, data: dict[str, Any]) -> RuntimeJobBase:
        raw_args = data.get("args", "{}")
        if isinstance(raw_args, str):
            data["args"] = json.loads(raw_args or "{}")
        return cls(**data)


class WorkerJobRecord(RuntimeJobBase):
    """
    Job consumed by the worker daemon.

    The worker should not load plans or infer step shape.
    It receives exactly one executable job envelope.
    """

    domain: ClassVar[str] = "job"
    kind: ClassVar[str] = "worker"

    daemon: Literal["worker"] = "worker"


class LedgerJobRecord(RuntimeJobBase):
    """
    Job consumed by the orchestrator/ledger daemon.

    This allows cursor/outcome handling to use the same hard-coded
    load pattern without sharing the worker job keyspace.
    """

    domain: ClassVar[str] = "job"
    kind: ClassVar[str] = "ledger"

    daemon: Literal["ledger"] = "ledger"