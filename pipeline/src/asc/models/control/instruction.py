from typing import ClassVar, Literal

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

    Public ``record_*`` upload fields are normalized by ``asc.upload.uploader``.
    The stored control model keeps only its canonical fields.
    """

    kind: ClassVar[str] = "instruction"

    model_config = ConfigDict(extra="allow")

    type: Literal["instruction"] = "instruction"
    identity: RedisIdentity = Field(default_factory=generate_identity)
    slug: RecordIdentity
    content: RequiredRecordContent
    assets: list[str] = Field(default_factory=list)

    @field_validator("assets", mode="before")
    @classmethod
    def validate_assets(cls, value: object) -> list[str]:
        return asset_list(value)


__all__ = ["Instruction"]
