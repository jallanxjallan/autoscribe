from __future__ import annotations

import json
from typing import Any, ClassVar, TypeVar

from pydantic import BaseModel

from asc.redis.key import RedisKey


T = TypeVar("T", bound="RedisModel")


class RedisModel(BaseModel):
    """Base for Redis-backed Pydantic hash records."""

    kind: ClassVar[str]
    suffix: ClassVar[str]

    @staticmethod
    def _require_text(value: object, *, field_name: str) -> str:
        if not isinstance(value, str):
            raise TypeError(f"{field_name} must be a string")
        value = value.strip()
        if not value:
            raise ValueError(f"{field_name} must be a non-empty string")
        return value

    @classmethod
    def redis_kind(cls) -> str:
        return cls._require_text(
            getattr(cls, "kind", None),
            field_name=f"{cls.__name__}.kind",
        )

    @classmethod
    def redis_suffix(cls) -> str:
        return cls._require_text(
            getattr(cls, "suffix", None),
            field_name=f"{cls.__name__}.suffix",
        )

    @classmethod
    def key_for_identity(cls, identity: str) -> RedisKey:
        identity = cls._require_text(identity, field_name="identity")
        return RedisKey.from_parts(
            cls.redis_kind(),
            identity,
            cls.redis_suffix(),
        )

    @classmethod
    def resolve_key(cls, value: str | RedisKey) -> RedisKey:
        if isinstance(value, RedisKey):
            return value

        text = cls._require_text(value, field_name="redis key or identity")

        if text.count(":") == 2:
            return RedisKey(text)

        return cls.key_for_identity(text)

    @classmethod
    def load(cls: type[T], value: str | RedisKey) -> T:
        key = cls.resolve_key(value)
        raw = key.hgetall()
        if not raw:
            raise RuntimeError(f"Redis hash record missing: {key}")
        return cls.load_redis(raw)

    @classmethod
    def load_redis(cls: type[T], data: dict[str, str]) -> T:
        return cls.model_validate(data)

    @property
    def redis_identity(self) -> str:
        return self._require_text(
            getattr(self, "identity", None),
            field_name=f"{self.__class__.__name__}.identity",
        )

    @property
    def redis_key(self) -> RedisKey:
        return self.__class__.key_for_identity(self.redis_identity)

    def dump_redis(self) -> dict[str, str]:
        dumped = self.model_dump(mode="json")
        return {
            key: _redis_value(value, field_name=key)
            for key, value in dumped.items()
        }

    def save(self, value: str | RedisKey | None = None) -> str:
        key = self.redis_key if value is None else self.__class__.resolve_key(value)
        key.hset(mapping=self.dump_redis())
        return str(key)

    def overwrite(self, value: str | RedisKey | None = None) -> str:
        return self.save(value)


def _redis_value(value: Any, *, field_name: str) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (str, int, float)):
        return str(value)

    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except TypeError as exc:
        raise TypeError(
            f"{field_name} could not be JSON-serialized for Redis hash storage"
        ) from exc