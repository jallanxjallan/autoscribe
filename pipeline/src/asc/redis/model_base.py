from __future__ import annotations

from typing import ClassVar, TypeVar

from pydantic import BaseModel

from asc.redis.key import RedisKey


T = TypeVar("T", bound="RedisModel")


class RedisModel(BaseModel):
    domain: ClassVar[str]

    @staticmethod
    def _require_text(value: object, *, field_name: str) -> str:
        if not isinstance(value, str):
            raise TypeError(f"{field_name} must be a string")
        value = value.strip()
        if not value:
            raise ValueError(f"{field_name} must be a non-empty string")
        return value

    @classmethod
    def _redis_kind(cls) -> str | None:
        value = getattr(cls, "kind", None)
        if value is None:
            return None
        return cls._require_text(value, field_name=f"{cls.__name__}.kind")

    @classmethod
    def key_for_identity(cls, identity: str) -> RedisKey:
        namespace = cls._require_text(cls.domain, field_name=f"{cls.__name__}.domain")
        identity = cls._require_text(identity, field_name="identity")
        kind = cls._redis_kind()
        if kind is None:
            return RedisKey.from_parts(namespace, identity)
        return RedisKey.from_parts(namespace, identity, kind)

    @classmethod
    def load(cls: type[T], identity: str) -> T:
        return cls.load_from_key(cls.key_for_identity(identity))

    @classmethod
    def load_from_key(cls: type[T], full_key: str | RedisKey) -> T:
        key = full_key if isinstance(full_key, RedisKey) else RedisKey(str(full_key))
        raw = key.get()
        if raw is None:
            raise RuntimeError(f"Redis JSON record missing: {key}")
        return cls.model_validate_json(raw)

    @property
    def redis_identity(self) -> str:
        return self._require_text(
            getattr(self, "identity", None),
            field_name=f"{self.__class__.__name__}.identity",
        )

    @property
    def redis_key(self) -> RedisKey:
        return self.__class__.key_for_identity(self.redis_identity)

    def save(self) -> str:
        key = self.redis_key
        key.set_json(self.model_dump(mode="json"))
        return str(key)

    def overwrite(self) -> str:
        key = self.redis_key
        key.set_json(self.model_dump(mode="json"))
        return str(key)
