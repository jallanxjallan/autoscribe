import json
from typing import ClassVar

from pydantic import ConfigDict, Field, model_validator

from asc.core.identity import generate_identity
from asc.core.timestamp import timestamp
from asc.redis.model_base import RedisModel


class CallRecord(RedisModel):
    """Persisted call record.

    Additional source fields supplied during enqueue are gathered into
    ``blob_json`` before persistence. This preserves source metadata for export
    consumers without allowing arbitrary fields into the stored Redis schema.
    """

    model_config = ConfigDict(extra="allow")

    kind: ClassVar[str] = "call"
    component: ClassVar[str] = "record"

    identity: str = Field(default_factory=generate_identity)
    source_identity: str
    plan_key: str
    content: str
    created_at: int = Field(default_factory=timestamp)
    blob_json: str = "{}"

    @model_validator(mode="after")
    def gather_extra_fields(self) -> "CallRecord":
        extras = dict(self.__pydantic_extra__ or {})
        if not extras:
            return self

        object.__setattr__(
            self,
            "blob_json",
            json.dumps(
                extras,
                ensure_ascii=False,
                sort_keys=True,
            ),
        )
        self.__pydantic_extra__.clear()
        return self


__all__ = ["CallRecord"]