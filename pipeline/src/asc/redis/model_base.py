import json
from typing import Any, ClassVar, TypeVar

from pydantic import BaseModel

from asc.redis.key import RedisKey


T = TypeVar("T", bound="RedisHashModel")


class RedisHashModel(BaseModel):
    """Shared behavior for Redis-backed Pydantic hash records.

    This class deliberately does not define a key shape. Subclasses choose
    whether identity resolves to a standalone key or a segmented artifact key.
    """

    @staticmethod
    def _require_text(value: object, *, field_name: str) -> str:
        if not isinstance(value, str):
            raise TypeError(f"{field_name} must be a string")
        value = value.strip()
        if not value:
            raise ValueError(f"{field_name} must be a non-empty string")
        return value

    @classmethod
    def resolve_key(cls, value: str | RedisKey) -> RedisKey:
        if isinstance(value, RedisKey):
            return value

        text = cls._require_text(value, field_name="redis key or identity")

        # A full Redis key has at least kind + identity. Anything without a
        # separator is treated as a bare identity and passed through the
        # subclass key policy.
        if RedisKey.SEP in text:
            return RedisKey(text)

        return cls.key_for_identity(text)

    @classmethod
    def key_for_identity(cls, identity: str) -> RedisKey:
        raise NotImplementedError(f"{cls.__name__} must define key_for_identity()")

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


class RedisRecord(RedisHashModel):
    """Standalone Redis hash model using kind:identity.

    Use this for records whose Redis identity is their own object identity.
    Ephemeral process-control messages should normally use RedisMessage from
    asc.redis.message_base, which is a semantic alias over this shape.
    """

    kind: ClassVar[str]

    @classmethod
    def redis_kind(cls) -> str:
        return cls._require_text(
            getattr(cls, "kind", None),
            field_name=f"{cls.__name__}.kind",
        )

    @classmethod
    def key_for_identity(cls, identity: str) -> RedisKey:
        identity = cls._require_text(identity, field_name="identity")
        return RedisKey.from_parts(cls.redis_kind(), identity)


class RedisArtifact(RedisRecord):
    """Segmented Redis hash model using kind:identity:suffix.

    Use this for durable artifacts that are owned by an external identity,
    such as call-owned cursor, index, result, or failure records.
    """

    suffix: ClassVar[str]

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


# Backward-compatible name for existing durable data models.
# Existing model classes that inherit RedisModel keep their current
# kind:identity:suffix key shape and do not need to be renamed.
RedisModel = RedisArtifact
RedisSegmentedModel = RedisArtifact


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


__all__ = [
    "RedisHashModel",
    "RedisRecord",
    "RedisArtifact",
    "RedisSegmentedModel",
    "RedisModel",
]
