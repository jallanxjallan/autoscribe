"""Reusable uploaded instruction control records."""

from __future__ import annotations

from typing import ClassVar

from pydantic import ConfigDict, Field

from asc.core.identity import generate_identity
from asc.models.helpers.upload import (
    RecordIdentity,
    RedisIdentity,
    RequiredRecordContent,
)
from asc.redis.model_base import RedisModel


class Instruction(RedisModel):
    """Canonical persisted instruction.

    Public upload envelopes are validated and converted by ``from_ndjson``.
    Redis hydration should reconstruct this canonical model without rerunning
    upload-boundary validation.
    """

    kind: ClassVar[str] = "instruction"
    component: ClassVar[str] = "record"

    model_config = ConfigDict(extra="forbid")

    identity: RedisIdentity = Field(default_factory=generate_identity)
    slug: RecordIdentity
    content: RequiredRecordContent




__all__ = ["Instruction"]
