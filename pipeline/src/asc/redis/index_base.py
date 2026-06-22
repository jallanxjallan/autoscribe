from typing import Callable, ClassVar, Literal, overload

from asc.redis.key import RedisKey


class RedisIndex:
    """
    Base class for Redis-backed operational indices.

    Subclasses may either:
    - define a fixed KEY class attribute, or
    - pass an explicit key string to __init__.

    Responsibilities:
    - bind a RedisKey instance
    - expose minimal existence / delete helpers
    - provide common helpers for hash-backed pointer indexes

    Non-responsibilities:
    - semantic interpretation of index contents
    - model loading policy
    - key formatting policy beyond accepting a full key string
    """

    KEY: ClassVar[str]

    def __init__(self, key: str | RedisKey | None = None) -> None:
        if key is None:
            self.key = RedisKey(self._default_key())
            return

        if isinstance(key, RedisKey):
            self.key = key
            return

        if isinstance(key, str):
            self.key = RedisKey(key)
            return

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

    def _r(self):
        return self.key._r()

    def exists(self) -> bool:
        return self.key.exists()

    def delete(self) -> int:
        return self.key.delete()

    def type(self) -> str:
        return self.key.type()


class FixedRedisIndex(RedisIndex):
    """Index with a single fixed Redis key declared at class level."""

    pass


class FixedRedisHashIndex(FixedRedisIndex):
    """
    Fixed-key HASH index storing string field -> string value pointers.

    This is the common base for registries like:
    - slug -> identity
    - alias -> identity
    - prompt_slug -> call_identity
    """

    def hget(self, field: str) -> str | None:
        field = self._require_text(field, field_name="field")
        return self.key.hget(field)

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
        value = self.key.hget(field)

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
        value = as_raw_key(value)
        existing = self.resolve_pointer(field)

        if existing is not None and existing != value and not overwrite:
            raise ValueError(
                f"{collision_label} collision for {field}: {existing} != {value}"
            )

        self.key.hset(field=field, value=value)
        return value

    def has_pointer(self, field: str) -> bool:
        field = self._require_text(field, field_name="field")
        return self.key.hget(field) is not None

    def delete_pointer(self, field: str) -> int:
        field = self._require_text(field, field_name="field")
        return self.key.hdel(field)

    def prune_missing_values(
        self,
        *,
        exists: Callable[[str], bool],
    ) -> int:
        """
        Remove hash fields whose stored value no longer resolves.

        Useful for maps like slug -> identity where the identity may later
        point to a missing Redis record.
        """
        raw = self.key.hgetall()
        removed = 0

        for field, value in raw.items():
            if not isinstance(field, str) or not isinstance(value, str):
                raise TypeError("hash index must contain str fields and str values")

            if not exists(value):
                self.key.hdel(field)
                removed += 1

        return removed