from __future__ import annotations

import json
from typing import Any, ClassVar, Self, TypeVar

from pydantic import BaseModel, model_validator

from asc.redis.key import RedisKey


T = TypeVar("T", bound="RedisModel")
_UNSET = object()


class RedisModel(BaseModel):
    """Base class for self-addressed Redis hash records.

    A RedisModel is persisted data. It must resolve to a three-segment Redis key:

        kind:identity:component
        kind:identity:ordinal

    ``component`` is a static class-level key segment such as ``record`` or
    ``index``. ``ordinal`` is an instance-level ordered key segment such as a
    step/result number. A model must use exactly one of them.
    """

    kind: ClassVar[str]
    component: ClassVar[str | int | None] = None

    identity: str

    @model_validator(mode="after")
    def validate_redis_key_contract(self) -> Self:
        # Force the key contract to be checked at model construction/load time,
        # not later when save() happens to be called.
        self.key_segment
        return self

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
        component: str | int | None | object = _UNSET,
        ordinal: str | int | None | object = _UNSET,
    ) -> RedisKey:
        return RedisKey.from_parts(
            cls.kind,
            identity,
            cls._resolve_key_segment(component=component, ordinal=ordinal),
        )

    @classmethod
    def _resolve_key_segment(
        cls,
        *,
        component: str | int | None | object = _UNSET,
        ordinal: str | int | None | object = _UNSET,
    ) -> str | int:
        if component is not _UNSET and ordinal is not _UNSET:
            raise ValueError(
                f"{cls.__name__} key requires either component or ordinal, not both"
            )

        if component is not _UNSET:
            return _validated_key_segment(component, "component", cls.__name__)

        if ordinal is not _UNSET:
            return _validated_key_segment(ordinal, "ordinal", cls.__name__)

        if cls.component is not None:
            return _validated_key_segment(cls.component, "component", cls.__name__)

        raise ValueError(f"{cls.__name__} key requires component or ordinal")

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
    def key_segment(self) -> str | int:
        component = self.__class__.component
        ordinal = getattr(self, "ordinal", None)

        if component is not None and ordinal is not None:
            raise ValueError(
                f"{self.__class__.__name__} defines both component and ordinal"
            )

        if component is None and ordinal is None:
            raise ValueError(
                f"{self.__class__.__name__} must define component or ordinal"
            )

        if ordinal is not None:
            return _validated_key_segment(ordinal, "ordinal", self.__class__.__name__)

        return _validated_key_segment(component, "component", self.__class__.__name__)

    @property
    def redis_key(self) -> RedisKey:
        return RedisKey.from_parts(self.kind, self.identity, self.key_segment)

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

    def save(self, *, ttl: int | None = None) -> str:
        if ttl is not None and ttl < 1:
            raise ValueError("save() ttl must be a positive integer")

        redis_key = self.redis_key
        redis_key.hset(mapping=self.dump_json())

        if ttl is not None:
            redis_key.expire(ttl)

        return redis_key.raw_key

    def overwrite(self, *, ttl: int | None = None) -> str:
        return self.save(ttl=ttl)

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


def _validated_key_segment(value: object, label: str, class_name: str) -> str | int:
    if value is None:
        raise ValueError(f"{class_name} {label} must not be None")

    if isinstance(value, int):
        return value

    text = str(value).strip()
    if not text:
        raise ValueError(f"{class_name} {label} must not be empty")

    return text


__all__ = ["RedisModel"]
