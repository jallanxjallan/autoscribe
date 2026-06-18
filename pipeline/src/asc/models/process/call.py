from __future__ import annotations

import json
from typing import ClassVar


from pydantic import ConfigDict, Field, model_validator

from asc.core.identity import generate_identity
from asc.redis.model_base import RedisModel
from asc.core.timestamp import timestamp


class Call(RedisModel):
    model_config = ConfigDict(extra="allow")

    kind: ClassVar[str] = "call"
    suffix: ClassVar[str] = "record"

    identity: str = Field(default_factory=generate_identity)
    source_identity: str
    content: str
    created_at: int = Field(default_factory=timestamp)
    blob_json: str = "{}"

    @model_validator(mode="after")
    def validate_kind(self) -> "Call":
        if self.kind != "call":
            raise ValueError(f"Call.kind must be 'call': {self.kind!r}")
        return self

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
