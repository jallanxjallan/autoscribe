from __future__ import annotations

from typing import Any, ClassVar, TypeVar

from pydantic import BaseModel

from asc.redis.key import RedisKey


T = TypeVar("T", bound="RedisModel")


class RedisModel(BaseModel):
    """Base for Redis-backed Pydantic records.

    Redis records are stored as hashes. Concrete models own all conversion
    details through Pydantic validators/serializers. The Redis adapter only
    calls dump_redis()/load_redis().
    """

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
        raw = key.hgetall()
        if not raw:
            raise RuntimeError(f"Redis hash record missing: {key}")
        return cls.load_redis(raw)

    @classmethod
    def load_redis(cls: type[T], data: dict[str, str]) -> T:
        """Validate a Redis hash mapping into a model instance."""

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
        """Return the model's Redis hash representation.

        Concrete models should use Pydantic field serializers to turn opaque
        payloads into explicit JSON-string fields such as metadata_json or
        engine_args_json before this method is called.
        """

        dumped = self.model_dump(mode="json")
        return {key: _redis_scalar(value, field_name=key) for key, value in dumped.items()}

    def save(self) -> str:
        key = self.redis_key
        key.hset(mapping=self.dump_redis())
        return str(key)

    def overwrite(self) -> str:
        return self.save()


def _redis_scalar(value: Any, *, field_name: str) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (str, int, float)):
        return str(value)
    raise TypeError(
        f"{field_name} serialized to {type(value).__name__}; "
        "Redis hash values must be scalar strings. Use a model field_serializer "
        "to produce an explicit *_json blob field."
    )
