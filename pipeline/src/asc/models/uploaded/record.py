from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import ConfigDict, Field, model_validator

from asc.core.identity import generate_identity
from asc.models.helpers.upload import (
    JsonObjectField,
    RecordIdentity,
    RedisIdentity,
    RequiredRecordContent,
    json_blob,
)
from asc.redis.model_base import RedisModel


class UploadedRecord(RedisModel):
    """Canonical uploaded prompt record.

    Prompt upload stores only the prompt itself. Plan selection belongs to the
    enqueue dispatch record and is deliberately not persisted here.

    Dict/list client metadata must be stored in explicit JSON-string fields so
    Redis hashes remain scalar-only.
    """

    namespace: ClassVar[str] = "uploaded"
    domain: ClassVar[str] = namespace
    kind: ClassVar[str] = "prompt"

    model_config = ConfigDict(extra="allow")

    record_type: Literal["prompt"]
    identity: RedisIdentity = Field(default_factory=generate_identity)
    slug: RecordIdentity
    record_identity: RecordIdentity
    record_content: RequiredRecordContent
    raw_record: JsonObjectField = Field(default_factory=dict)
    source_json: str = ""

    @model_validator(mode="before")
    @classmethod
    def normalize_upload_shape(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value

        normalized = dict(value)
        normalized.pop("identity", None)
        normalized.pop("plan_slug", None)

        if "record_type" not in normalized and "type" in normalized:
            normalized["record_type"] = normalized["type"]

        if "record_identity" not in normalized:
            for key in ("prompt_slug", "slug", "identifier"):
                if key in normalized:
                    normalized["record_identity"] = normalized[key]
                    break

        # RedisModel and slugmap helpers use a concrete `slug` field. Keep it
        # as data, not a property alias, and derive it from the canonical upload
        # identity so both contracts stay aligned.
        if "record_identity" in normalized:
            normalized["slug"] = normalized["record_identity"]

        if "record_content" not in normalized:
            for key in ("content", "prompt", "text"):
                if key in normalized:
                    normalized["record_content"] = normalized[key]
                    break

        # `source` is commonly emitted as an object by the client. Do not leave
        # it in model_extra, because RedisModel will then try to write a dict
        # directly into a Redis hash. Preserve it as a scalar JSON blob instead.
        if "source" in normalized and "source_json" not in normalized:
            normalized["source_json"] = json_blob(normalized.pop("source"), "source_json")
        else:
            normalized.pop("source", None)

        raw_record = dict(normalized)
        raw_record.pop("plan_slug", None)
        normalized.setdefault("raw_record", raw_record)
        return normalized

    @model_validator(mode="after")
    def strip_prompt_only_extras(self) -> "UploadedRecord":
        # Pydantic keeps unknown keys in model_extra because extra="allow".
        # Remove aliases/client-only fields after they have been folded into the
        # canonical contract or explicit *_json blobs.
        if self.model_extra:
            for key in ("type", "identifier", "prompt_slug", "content", "prompt", "text", "source", "plan_slug"):
                self.model_extra.pop(key, None)
        return self


__all__ = ["UploadedRecord"]
