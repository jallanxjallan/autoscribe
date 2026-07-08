import json
from typing import Any, ClassVar, TypeVar

from pydantic import BaseModel

from asc.redis.key import RedisKey


T = TypeVar("T", bound="RedisModel")
_UNSET = object()


class RedisModel(BaseModel):
    kind: ClassVar[str]
    suffix: ClassVar[str | int | None] = None
    identity: str

    @classmethod
    def redis_key_from_raw(cls, value: str | RedisKey) -> RedisKey:
        if isinstance(value, RedisKey):
            return value
        return RedisKey(value)

    @classmethod
    def key_for_identity(
        cls,
        identity: str,
        *,
        kind: str | None = None,
        suffix: str | int | None | object = _UNSET,
    ) -> RedisKey:
        return RedisKey.from_parts(
            cls.kind if kind is None else kind,
            identity,
            cls.suffix if suffix is _UNSET else suffix,
        )

    @classmethod
    def load(cls: type[T], key: str | RedisKey) -> T:
        redis_key = cls.redis_key_from_raw(key)
        raw = redis_key.hgetall()
        if not raw:
            raise RuntimeError(f"Redis hash record missing: {redis_key.raw_key}")
        return cls.load_redis(raw)

    @classmethod
    def load_redis(cls: type[T], data: dict[str, str]) -> T:
        return cls.model_validate(data)

    @property
    def redis_key(self) -> RedisKey:
        return self.__class__.key_for_identity(self.identity)

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
                    f"{field_name} could not be JSON-serialized for Redis hash storage"
                ) from exc

        dumped = self.model_dump(mode="json")
        return {
            field_name: redis_value(value, field_name=field_name)
            for field_name, value in dumped.items()
        }

    def save(
        self,
        key: str | RedisKey | None = None,
        *,
        kind: str | None = None,
        identity: str | None = None,
        suffix: str | int | None | object = _UNSET,
        ttl: int | None = None,
    ) -> str:
        if key is not None and (
            kind is not None or identity is not None or suffix is not _UNSET
        ):
            raise ValueError("save() accepts either a raw key or key parts, not both")

        if ttl is not None and ttl < 1:
            raise ValueError("save() ttl must be a positive integer")

        redis_key = (
            self.__class__.key_for_identity(
                self.identity if identity is None else identity,
                kind=kind,
                suffix=suffix,
            )
            if key is None
            else self.__class__.redis_key_from_raw(key)
        )
        redis_key.hset(mapping=self.dump_json())
        if ttl is not None:
            redis_key.expire(ttl)
        return redis_key.raw_key

    def overwrite(
        self,
        key: str | RedisKey | None = None,
        *,
        kind: str | None = None,
        identity: str | None = None,
        suffix: str | int | None | object = _UNSET,
        ttl: int | None = None,
    ) -> str:
        return self.save(key, kind=kind, identity=identity, suffix=suffix, ttl=ttl)

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


__all__ = ["RedisModel"]
