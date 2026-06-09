from __future__ import annotations

from asc.models.runtime.content import RuntimeContentRecord, RuntimeContentRef
from asc.models.runtime.step import RuntimeStepRecord, RuntimeStepRef
from asc.redis.index_base import FixedRedisHashIndex
from asc.redis.key import RedisKey


def _positive_int(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    if value < 1:
        raise ValueError(f"{field_name} must be greater than zero")
    return value


def _identity(value: object, field_name: str = "identity") -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} must be non-empty")
    if ":" in text:
        raise ValueError(f"{field_name} must be a single Redis identity segment")
    return text


def _full_key(value: object, field_name: str) -> str:
    if isinstance(value, RedisKey):
        text = str(value)
    elif isinstance(value, str):
        text = value.strip()
    else:
        raise TypeError(f"{field_name} must be a Redis key string")
    if not text:
        raise ValueError(f"{field_name} must be non-empty")
    RedisKey(text)
    return text


class RuntimeContentIndex(FixedRedisHashIndex):
    """Hash index of content position -> full RuntimeContentRecord Redis key."""

    def __init__(self, identity: str) -> None:
        super().__init__(str(RedisKey.from_parts("runtime", _identity(identity), "content-index")))

    def bind_key(self, position: int, full_key: str | RedisKey) -> str:
        position = _positive_int(position, "position")
        key = _full_key(full_key, "content key")
        self.bind_pointer(str(position), key, overwrite=True, collision_label="content position")
        return key

    def resolve_key(self, position: int) -> str:
        position = _positive_int(position, "position")
        return self.resolve_pointer(str(position), require=True, missing_label="content index")

    def bind_ref(self, ref: RuntimeContentRef) -> None:
        self.bind_key(
            ref.position,
            RuntimeContentRecord.key_for_position(identity=ref.identity, position=ref.position),
        )

    def bind_content(self, ref: RuntimeContentRef) -> None:
        self.bind_ref(ref)

    def resolve_ref(self, position: int) -> RuntimeContentRef:
        record = RuntimeContentRecord.load_from_key(self.resolve_key(position))
        if record is None:
            raise RuntimeError(f"content record missing for position {position}")
        return record.to_ref()

    def hkeys(self) -> list[str]:
        return self.key.hkeys()

    def hlen(self) -> int:
        return self.key.hlen()


class RuntimeStepIndex(FixedRedisHashIndex):
    """Hash index of step number -> full RuntimeStepRecord Redis key."""

    def __init__(self, identity: str) -> None:
        super().__init__(str(RedisKey.from_parts("runtime", _identity(identity), "step-index")))

    def bind_key(self, step_number: int, full_key: str | RedisKey) -> str:
        step_number = _positive_int(step_number, "step_number")
        key = _full_key(full_key, "step key")
        self.bind_pointer(str(step_number), key, overwrite=True, collision_label="step number")
        return key

    def resolve_key(self, step_number: int) -> str:
        step_number = _positive_int(step_number, "step_number")
        return self.resolve_pointer(str(step_number), require=True, missing_label="step index")

    def bind_ref(self, ref: RuntimeStepRef) -> None:
        self.bind_key(ref.step_number, RuntimeStepRecord.key_for_step(ref.identity, ref.step_number))

    def bind_step(self, ref: RuntimeStepRef) -> None:
        self.bind_ref(ref)

    def resolve_ref(self, step_number: int) -> RuntimeStepRef:
        record = RuntimeStepRecord.load_from_key(self.resolve_key(step_number))
        if record is None:
            raise RuntimeError(f"step record missing for step {step_number}")
        return record.to_ref()

    def hkeys(self) -> list[str]:
        return self.key.hkeys()

    def hlen(self) -> int:
        return self.key.hlen()


__all__ = ["RuntimeContentIndex", "RuntimeStepIndex"]
