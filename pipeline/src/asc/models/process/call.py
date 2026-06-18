from __future__ import annotations

import json
from typing import Any, ClassVar

from pydantic import ConfigDict, model_validator

from asc.redis.model_base import RedisModel


class Call(RedisModel):
    model_config = ConfigDict(extra="allow")

    allowed_record_types: ClassVar[set[str]] = {"call", "prompt", "document"}

    identity: str
    source_identity: str
    content: str
    blob_json: str = "{}"

    @classmethod
    def from_ndjson(cls, record: dict[str, Any], *, identity: str) -> "Call":
        record_type = cls._required(record, "record_type")
        if record_type not in cls.allowed_record_types:
            allowed = ", ".join(sorted(cls.allowed_record_types))
            raise ValueError(
                f"unsupported call record_type: {record_type!r}; expected one of: {allowed}"
            )

        payload = dict(record)
        payload.pop("record_type")

        return cls(
            identity=identity,
            source_identity=cls._required(payload, "record_identity"),
            content=cls._required(payload, "record_content"),
            **payload,
        )

    @staticmethod
    def _required(record: dict[str, Any], field: str) -> Any:
        try:
            value = record.pop(field)
        except KeyError as exc:
            raise ValueError(f"call ndjson record missing required field: {field}") from exc

        if value is None:
            raise ValueError(f"call ndjson record has empty required field: {field}")

        if isinstance(value, str) and not value.strip():
            raise ValueError(f"call ndjson record has empty required field: {field}")

        return value

    @model_validator(mode="after")
    def gather_extra_fields(self) -> "Call":
        extras = dict(self.__pydantic_extra__ or {})
        if not extras:
            return self

        object.__setattr__(
            self,
            "blob_json",
            json.dumps(extras, ensure_ascii=False, sort_keys=True),
        )
        self.__pydantic_extra__.clear()
        return self


__all__ = ["Call"]
