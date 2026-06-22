import json
from typing import Any, ClassVar, TypeVar

from pydantic import BaseModel

from asc.redis.key import RedisKey


T = TypeVar("T", bound="RedisModel")


class RedisModel(BaseModel):
    """Shared behavior for Redis-backed Pydantic hash records.

    Subclasses define a required kind. Model keys use the two-segment shape::

        kind:identity

    This class deliberately does not guess whether a string is an identity or
    a full Redis key. Model instances build keys from their own identity.
    Loading and explicit save targets accept full raw keys or RedisKey objects.
    """

    kind: ClassVar[str]

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
    def redis_key_from_raw(cls, value: str | RedisKey) -> RedisKey:
        """Parse a full Redis key string or pass through a RedisKey object.

        This intentionally does not accept bare identities. Use
        key_for_identity(identity) when constructing a key from model identity.
        """

        if isinstance(value, RedisKey):
            return value

        return RedisKey(cls._require_text(value, field_name="redis key"))

    @classmethod
    def key_for_identity(cls, identity: str) -> RedisKey:
        identity = cls._require_text(identity, field_name="identity")
        return RedisKey.from_parts(cls.redis_kind(), identity)

    @classmethod
    def load(cls: type[T], key: str | RedisKey) -> T:
        redis_key = cls.redis_key_from_raw(key)
        raw = redis_key.hgetall()
        if not raw:
            raise RuntimeError(f"Redis hash record missing: {redis_key}")
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

    @property
    def raw_key(self) -> str:
        return self.redis_key.raw_key
    
    def dump_json(self) -> dict[str, str]:
        dumped = self.model_dump(mode="json")
        return {
            field_name: _redis_value(value, field_name=field_name)
            for field_name, value in dumped.items()
        }



def save(self, key: str | RedisKey | None = None) -> str:
    redis_key = (
        self.redis_key
        if key is None
        else self.__class__.redis_key_from_raw(key)
    )
    redis_key.hset(mapping=self.dump(output="redis"))
    return redis_key.raw_key

    def save(self, key: str | RedisKey | None = None) -> str:
        redis_key = self.redis_key if key is None else self.__class__.redis_key_from_raw(key)
        redis_key.hset(mapping=self.dump_redis())
        return redis_key.raw_key

    def overwrite(self, key: str | RedisKey | None = None) -> str:
        return self.save(key)


# Compatibility alias for code that still imports the old segmented-name base.
RedisArtifact = RedisModel


def _redis_value(value: Any, *, field_name: str) -> str:
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
            f"{field_name} could not be JSON-serialized for Redis hash storage"
        ) from exc


__all__ = ["RedisModel", "RedisArtifact"]
