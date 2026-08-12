from __future__ import annotations

import json
from typing import Any, ClassVar, TypeVar

from pydantic import BaseModel, field_validator

from asc.redis.key import RedisKey


T = TypeVar("T", bound="RedisMessage")


class RedisMessage(BaseModel):
    """Base class for transient Redis queue/list payloads.

    RedisMessage is deliberately not a RedisModel.

    Messages are short-lived transport hashes addressed only by:

        kind:<identity>

    They do not have component, ordinal, or suffix semantics. Task generates a
    fresh identity. Outcome reuses the task identity.

    RedisModel is for durable records addressed by:

        kind:<identity>:component
        kind:<identity>:ordinal
    """

    kind: ClassVar[str]
    identity: str

    @classmethod
    def redis_key_from_raw(cls, value: str | RedisKey) -> RedisKey:
        if isinstance(value, RedisKey):
            return value
        return RedisKey(value)

    @classmethod
    def load(cls: type[T], key: str | RedisKey) -> T:
        redis_key = cls.redis_key_from_raw(key)
        raw = redis_key.hgetall()
        if not raw:
            raise RuntimeError(f"Redis hash message missing: {redis_key.raw_key}")
        return cls.load_redis(raw)

    @classmethod
    def load_redis(cls: type[T], data: dict[str, str]) -> T:
        return cls.model_validate(data)

    @property
    def redis_key(self) -> RedisKey:
        return RedisKey.from_parts(self.kind, self.identity, None)

    @property
    def raw_key(self) -> str:
        return self.redis_key.raw_key

    def dump_json(self) -> dict[str, str]:
        def redis_value(value: Any, *, field_name: str) -> str:
            if value is None:
                return ""
            if isinstance(value, RedisKey):
                return value.raw_key
            if isinstance(value, bool):
                return "true" if value else "false"
            if isinstance(value, (str, int, float)):
                return str(value)

            try:
                return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            except TypeError as exc:
                raise TypeError(
                    f"{field_name} could not be JSON-serialized for Redis message storage"
                ) from exc

        dumped = self.model_dump(mode="json")
        return {
            field_name: redis_value(value, field_name=field_name)
            for field_name, value in dumped.items()
        }

    def save(self, *, ttl: int | None = None) -> str:
        if ttl is not None and ttl < 1:
            raise ValueError("save() ttl must be a positive integer")

        redis_key = self.redis_key
        redis_key.hset(mapping=self.dump_json())

        if ttl is not None:
            redis_key.expire(ttl)

        return redis_key.raw_key

    def exists(self) -> bool:
        return self.redis_key.exists()

    def delete(self) -> int:
        return self.redis_key.delete()

    def type(self) -> str:
        return self.redis_key.type()

    def ttl(self) -> int:
        return self.redis_key.ttl()

    def expire(self, seconds: int) -> bool:
        if seconds < 1:
            raise ValueError("expire() requires positive int seconds")
        return self.redis_key.expire(seconds)

    @field_validator("claimed_at", mode="before", check_fields=False)
    @classmethod
    def empty_optional_ints_are_none(cls, value: object) -> object:
        if value == "":
            return None
        return value


__all__ = ["RedisMessage"]