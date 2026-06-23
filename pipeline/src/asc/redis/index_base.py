from typing import Callable, ClassVar, Literal, overload

from asc.redis.key import RedisKey
from asc.redis.primitives import hashes, keys


class RedisIndex:
    KEY: ClassVar[str]

    def __init__(self, key: str | RedisKey | None = None) -> None:
        if key is None:
            self.key = RedisKey(self._default_key())
        elif isinstance(key, RedisKey):
            self.key = key
        elif isinstance(key, str):
            self.key = RedisKey(key)
        else:
            raise TypeError("key must be a str, RedisKey, or None")

    @classmethod
    def _default_key(cls) -> str:
        key = getattr(cls, "KEY", None)
        if not isinstance(key, str) or not key:
            raise TypeError(f"{cls.__name__} must define non-empty KEY")
        return key

    @staticmethod
    def _require_text(value: object, *, field_name: str) -> str:
        if not isinstance(value, str):
            raise TypeError(f"{field_name} must be a string")
        value = value.strip()
        if not value:
            raise ValueError(f"{field_name} must be a non-empty string")
        return value

    @property
    def raw_key(self) -> str:
        return self.key.raw_key

    def __str__(self) -> str:
        return self.raw_key

    def exists(self) -> bool:
        return keys.exists(self.key)

    def delete(self) -> int:
        return keys.delete(self.key)

    def type(self) -> str:
        return keys.type(self.key)

    def ttl(self) -> int:
        return keys.ttl(self.key)

    def expire(self, seconds: int) -> bool:
        return keys.expire(self.key, seconds)


class FixedRedisIndex(RedisIndex):
    pass


class FixedRedisHashIndex(FixedRedisIndex):
    def hget(self, field: str) -> str | None:
        field = self._require_text(field, field_name="field")
        return hashes.hget(self.key, field)

    def hset(self, *, field: str, value: str) -> int:
        field = self._require_text(field, field_name="field")
        value = self._require_text(value, field_name="value")
        return hashes.hset(self.key, field=field, value=value)

    def hdel(self, field: str) -> int:
        field = self._require_text(field, field_name="field")
        return hashes.hdel(self.key, field)

    def hgetall(self) -> dict[str, str]:
        return hashes.hgetall(self.key)

    def hkeys(self) -> list[str]:
        return hashes.hkeys(self.key)

    def hlen(self) -> int:
        return hashes.hlen(self.key)

    @overload
    def resolve_pointer(
        self,
        field: str,
        *,
        require: Literal[True],
        missing_label: str = "index",
    ) -> str: ...

    @overload
    def resolve_pointer(
        self,
        field: str,
        *,
        require: Literal[False] = False,
        missing_label: str = "index",
    ) -> str | None: ...

    def resolve_pointer(
        self,
        field: str,
        *,
        require: bool = False,
        missing_label: str = "index",
    ) -> str | None:
        field = self._require_text(field, field_name="field")
        value = self.hget(field)

        if value is None and require:
            raise KeyError(f"{missing_label} miss for {field}")

        return value

    def bind_pointer(
        self,
        field: str,
        value: str | RedisKey,
        *,
        overwrite: bool = False,
        collision_label: str = "field",
    ) -> str:
        field = self._require_text(field, field_name="field")
        normalized_value = (
            value.raw_key
            if isinstance(value, RedisKey)
            else self._require_text(value, field_name="value")
        )

        existing = self.resolve_pointer(field)

        if existing is not None and existing != normalized_value and not overwrite:
            raise ValueError(
                f"{collision_label} collision for {field}: "
                f"{existing} != {normalized_value}"
            )

        self.hset(field=field, value=normalized_value)
        return normalized_value

    def has_pointer(self, field: str) -> bool:
        field = self._require_text(field, field_name="field")
        return self.hget(field) is not None

    def delete_pointer(self, field: str) -> int:
        field = self._require_text(field, field_name="field")
        return self.hdel(field)

    def prune_missing_values(
        self,
        *,
        exists: Callable[[str], bool],
    ) -> int:
        removed = 0

        for field, value in self.hgetall().items():
            if not exists(value):
                self.hdel(field)
                removed += 1

        return removed
