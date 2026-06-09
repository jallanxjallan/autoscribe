from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import ConfigDict, Field, model_validator

from asc.core.identity import generate_identity
from asc.models.helpers.upload import OptionalRecordContent, RecordIdentity, RedisIdentity
from asc.redis.model_base import RedisModel


class PlanRecord(RedisModel):
    """Uploaded reusable plan control asset.

    The wrapper contract is record_type / record_identity / record_content.
    Step definitions and any other plan metadata are pass-through extras.
    """

    namespace: ClassVar[str] = "control"
    domain: ClassVar[str] = namespace
    kind: ClassVar[str] = "plan"

    model_config = ConfigDict(extra="allow")

    type: Literal["plan"] = "plan"
    record_type: Literal["plan"] = "plan"
    identity: RedisIdentity = Field(default_factory=generate_identity)
    slug: RecordIdentity
    record_identity: RecordIdentity
    record_content: OptionalRecordContent = ""

    @model_validator(mode="before")
    @classmethod
    def normalize_upload_shape(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        if "record_identity" in normalized:
            normalized["slug"] = normalized["record_identity"]
        elif "slug" in normalized:
            normalized["record_identity"] = normalized["slug"]
        return normalized


__all__ = ["PlanRecord"]
