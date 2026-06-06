from __future__ import annotations

from typing import Any, ClassVar, Literal, Mapping

from pydantic import ConfigDict, Field, field_validator, model_validator

from asc.core.timestamp import timestamp
from asc.models.helpers.plain import plain_non_empty_string, redis_key_segment_text, slug_like_text
from asc.redis.model_base import RedisModel


class RuntimeCallRecord(RedisModel):
    """
    Redis-persisted runtime call anchor for one uploaded prompt record.

    The uploaded NDJSON row is preserved in raw_record for custody/export, but
    execution reads prompt text from the runtime content chain, not from the call
    record. Enqueue seeds content position 1 from source_content before workers
    run.
    """

    model_config = ConfigDict(extra="ignore")

    domain: ClassVar[str] = "call"
    kind: ClassVar[str] = "record"

    type: Literal["runtime-call"] = "runtime-call"
    identity: str
    identifier: str
    plan_slug: str
    raw_record: dict[str, Any] = Field(default_factory=dict)
    created_at: int = Field(default_factory=timestamp)

    @model_validator(mode="before")
    @classmethod
    def materialize_from_prompt_row(cls, value: object) -> object:
        if not isinstance(value, Mapping):
            return value

        normalized = dict(value)

        # Already-persisted runtime records are loaded as-is.
        if normalized.get("type") == "runtime-call":
            return normalized

        raw_record = dict(normalized)

        record_type = plain_non_empty_string(raw_record.get("type"), "type")
        if record_type != "prompt":
            raise ValueError(f"runtime call requires type='prompt', got {record_type!r}")

        # The stream/upload gatekeeper also checks these global fields. The
        # runtime model repeats the check so direct enqueue_record() calls cannot
        # bypass the persisted-record contract.
        identifier = plain_non_empty_string(raw_record.get("identifier"), "identifier")
        plan_slug = slug_like_text(raw_record.get("plan_slug"), "plan_slug")
        plain_non_empty_string(raw_record.get("content"), "content")

        return {
            "type": "runtime-call",
            "identity": normalized.get("identity"),
            "identifier": identifier,
            "plan_slug": plan_slug,
            "raw_record": raw_record,
            "created_at": normalized.get("created_at", timestamp()),
        }

    @field_validator("identity", mode="before")
    @classmethod
    def validate_identity(cls, value: object) -> str:
        return redis_key_segment_text(value, "identity")

    @field_validator("identifier", mode="before")
    @classmethod
    def validate_identifier(cls, value: object) -> str:
        return plain_non_empty_string(value, "identifier")

    @field_validator("plan_slug", mode="before")
    @classmethod
    def validate_plan_slug(cls, value: object) -> str:
        return slug_like_text(value, "plan_slug")

    @field_validator("raw_record", mode="before")
    @classmethod
    def validate_raw_record(cls, value: object) -> dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, Mapping):
            raise ValueError("raw_record must be an object")
        return dict(value)

    @classmethod
    def from_raw_record(
        cls,
        *,
        identity: str,
        raw_record: Mapping[str, Any],
    ) -> "RuntimeCallRecord":
        return cls(identity=identity, **dict(raw_record))

    @property
    def call_identity(self) -> str:
        return self.identity

    @property
    def source_content(self) -> str:
        """Return the uploaded source text used to seed content position 1."""

        return plain_non_empty_string(self.raw_record.get("content"), "raw_record.content")


CallRecord = RuntimeCallRecord

__all__ = ["CallRecord", "RuntimeCallRecord"]
