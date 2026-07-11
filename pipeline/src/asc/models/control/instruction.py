"""Reusable uploaded instruction control records."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar

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

    @classmethod
    def from_ndjson(
        cls,
        record: Mapping[str, Any],
        *,
        identity: str | None = None,
    ) -> "Instruction":
        """Validate an instruction upload envelope and build its stored model."""

        record_type = record.get("record_type")
        if record_type != "instruction":
            raise ValueError(
                f"record_type must be 'instruction', got {record_type!r}"
            )

        try:
            slug = record["record_identity"]
            content = record["record_content"]
        except KeyError as exc:
            raise ValueError(
                f"instruction upload missing required field: {exc.args[0]}"
            ) from exc

        return cls.model_validate(
            {
                "identity": identity or generate_identity(),
                "slug": slug,
                "content": content,
            }
        )


__all__ = ["Instruction"]
