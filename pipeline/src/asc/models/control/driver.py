from __future__ import annotations

from typing import Any, ClassVar, Literal, cast, get_args

from asc.core.identity import generate_identity

from pydantic import ConfigDict, Field, field_validator, model_validator

from asc.models.helpers.plain import (
    plain_non_empty_string,
    redis_key_segment_text,
    slug_like_text,
)
from asc.models.helpers.upload import asset_list, optional_text, plain_object
from asc.redis.model_base import RedisModel
from asc.streams.upload_normalizer import prepare_upload_record


DriverType = Literal["llm", "rag", "tool", "script"]
DriverArgs = dict[str, Any]

_DRIVER_TYPES: tuple[str, ...] = get_args(DriverType)
_DRIVER_TYPE_SET = frozenset(_DRIVER_TYPES)



def normalized_driver_type(value: object) -> DriverType:
    driver_type_value = plain_non_empty_string(value, "driver_type").strip().lower()

    if driver_type_value not in _DRIVER_TYPE_SET:
        allowed = ", ".join(_DRIVER_TYPES)
        raise ValueError(f"driver_type must be one of: {allowed}")

    return cast(DriverType, driver_type_value)



def normalize_args(value: object) -> DriverArgs:
    return plain_object(value, "args")


class DriverRecord(RedisModel):
    """
    Uploaded reusable driver control asset.

    Upload records must arrive as canonical JSON objects with top-level
    type="driver" and identifier="drv.some-slug.x1y2z3". Intake may derive
    slug from identifier, but it does not rescue nested or aliased model fields.

    Driver content is not part of the driver contract. If a producer emits a
    content field, it is preserved in raw_record and otherwise ignored.
    """

    namespace: ClassVar[str] = "control"
    domain: ClassVar[str] = namespace
    kind: ClassVar[str] = "driver"

    model_config = ConfigDict(extra="ignore")

    type: Literal["driver"]
    identity: str = Field(default_factory=generate_identity)
    identifier: str
    identifier_kind: Literal["slug"]
    slug: str
    client: str
    driver_type: DriverType
    args: DriverArgs = Field(default_factory=dict)
    description: str = ""
    assets: list[str] = Field(default_factory=list)
    source: dict[str, Any] = Field(default_factory=dict)
    raw_record: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def prepare_record(cls, value: object) -> object:
        return prepare_upload_record(
            value,
            allowed_types={"driver"},
            identifier_kinds={"slug"},
        )

    @field_validator("identity", mode="before")
    @classmethod
    def validate_identity(cls, value: object) -> str:
        return redis_key_segment_text(value, "identity")

    @field_validator("identifier", mode="before")
    @classmethod
    def validate_identifier(cls, value: object) -> str:
        return plain_non_empty_string(value, "identifier").strip()

    @field_validator("slug", mode="before")
    @classmethod
    def validate_slug(cls, value: object) -> str:
        return slug_like_text(value)

    @field_validator("client", mode="before")
    @classmethod
    def validate_client(cls, value: object) -> str:
        client = plain_non_empty_string(value, "client").strip().lower()

        if any(char.isspace() for char in client):
            raise ValueError("client must be a machine-readable name without whitespace")

        return client

    @field_validator("driver_type", mode="before")
    @classmethod
    def validate_driver_type(cls, value: object) -> DriverType:
        return normalized_driver_type(value)

    @field_validator("args", mode="before")
    @classmethod
    def validate_args(cls, value: object) -> DriverArgs:
        return normalize_args(value)

    @field_validator("description", mode="before")
    @classmethod
    def validate_description(cls, value: object) -> str:
        return optional_text(value, "description")

    @field_validator("assets", mode="before")
    @classmethod
    def validate_assets(cls, value: object) -> list[str]:
        return asset_list(value)

    @field_validator("source", "raw_record", mode="before")
    @classmethod
    def validate_plain_object(cls, value: object) -> dict[str, Any]:
        return plain_object(value, "object")


__all__ = ["DriverRecord", "DriverType", "DriverArgs"]
