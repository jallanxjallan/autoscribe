from collections.abc import Mapping
from typing import Any, ClassVar, Literal

from pydantic import ConfigDict, Field, field_validator

from asc.core.identity import generate_identity
from asc.models.helpers.upload import (
    RecordIdentity,
    RedisIdentity,
    RequiredRecordContent,
    asset_list,
)
from asc.redis.model_base import RedisModel


class Instruction(RedisModel):
    """Uploaded reusable instruction control asset.

    Upload accepts the public NDJSON record shape::

        {
            "record_type": "instruction",
            "record_identity": "ins.example.slug",
            "record_content": "instruction text",
            ...extra metadata...
        }

    The stored Redis model keeps the canonical fields used by the runtime:
    ``type``, ``identity``, ``slug``, ``content``, and any allowed extra
    metadata from the upload record.
    """

    kind: ClassVar[str] = "instruction"

    model_config = ConfigDict(extra="allow")

    type: Literal["instruction"] = "instruction"
    identity: RedisIdentity = Field(default_factory=generate_identity)
    slug: RecordIdentity
    content: RequiredRecordContent
    assets: list[str] = Field(default_factory=list)

    @classmethod
    def from_ndjson(
        cls,
        record: Mapping[str, Any],
        *,
        identity: str | None = None,
    ) -> "Instruction":
        """Build an Instruction from the upload NDJSON envelope.

        ``asc.upload.upload_records`` validates that ``record_type``,
        ``record_identity``, and ``record_content`` are present before calling
        this method. This method performs only the shape conversion from public
        upload fields to the stored model fields.
        """

        data = dict(record)

        record_type = data.pop("record_type", "instruction")
        if record_type != "instruction":
            raise ValueError(f"record_type must be 'instruction', got {record_type!r}")

        record_identity = data.pop("record_identity")
        record_content = data.pop("record_content")

        data.pop("identity", None)

        data["type"] = "instruction"
        data["identity"] = identity or generate_identity()
        data["slug"] = record_identity
        data["content"] = record_content

        return cls.model_validate(data)

    @field_validator("assets", mode="before")
    @classmethod
    def validate_assets(cls, value: object) -> list[str]:
        return asset_list(value)


__all__ = ["Instruction"]
