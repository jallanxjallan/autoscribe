"""Short-lived process marker for worker steps in progress.

A response-index step slot stores this model's Redis key after the orchestrator
assigns a worker task and before the worker returns a result or failure.  The
marker points back to the actual worker task key and carries a timestamp for
watchdogs.
"""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import ConfigDict, Field, field_serializer, field_validator

from asc.core.timestamp import timestamp
from asc.models.helpers.plain import plain_non_empty_string, redis_key_segment_text
from asc.redis.key import RedisKey
from asc.redis.model_base import RedisModel


DEFAULT_IN_PROCESS_TTL_SECONDS = 60 * 60


class InProcess(RedisModel):
    """Short-lived marker for a worker-owned step slot.

    Key shape:
        in_process:<process_identity>:step.<step_number>

    The model is deliberately tiny.  It is watchdog/process-progress state, not
    worker output.  A worker outcome should replace the corresponding response
    index slot with a result or failure key.
    """

    model_config = ConfigDict(extra="forbid")

    # ``RedisModel.domain`` is not used for this model's key construction; the
    # marker kind is the first Redis key segment by design.
    domain: ClassVar[str] = "in_process"
    kind: ClassVar[str] = "in_process"
    suffix_prefix: ClassVar[str] = "step"
    default_ttl_seconds: ClassVar[int] = DEFAULT_IN_PROCESS_TTL_SECONDS

    type: Literal["in_process"] = "in_process"

    identity: str
    step_number: int = Field(ge=1)
    task_key: str
    cursor_key: str
    created_at: int = Field(default_factory=timestamp)

    @field_validator("identity", mode="before")
    @classmethod
    def validate_identity(cls, value: object) -> str:
        return redis_key_segment_text(value, "identity")

    @field_validator("step_number", mode="before")
    @classmethod
    def validate_step_number(cls, value: object) -> int:
        number = int(value)
        if number < 1:
            raise ValueError("step_number must be >= 1")
        return number

    @field_validator("task_key", "cursor_key", mode="before")
    @classmethod
    def validate_full_key(cls, value: object) -> str:
        text = plain_non_empty_string(value, "Redis key")
        if ":" not in text:
            raise ValueError(f"expected full Redis key, got {text!r}")
        RedisKey(text)
        return text

    @field_serializer("step_number", "created_at")
    def serialize_int(self, value: int) -> str:
        return str(value)

    @classmethod
    def key_for_step(cls, identity: str, step_number: int) -> RedisKey:
        identity = redis_key_segment_text(identity, "identity")
        number = int(step_number)
        if number < 1:
            raise ValueError("step_number must be >= 1")
        return RedisKey.from_parts(cls.kind, identity, f"{cls.suffix_prefix}.{number}")

    @classmethod
    def key_for_identity(cls, identity: str) -> RedisKey:
        raise TypeError("InProcess requires step_number; use key_for_step(identity, step_number)")

    @property
    def redis_key(self) -> RedisKey:
        return self.key_for_step(self.identity, self.step_number)

    def save(self, ttl_seconds: int | None = DEFAULT_IN_PROCESS_TTL_SECONDS) -> str:
        key = self.redis_key
        key.hset(mapping=self.dump_redis())
        if ttl_seconds is not None and int(ttl_seconds) > 0:
            key.expire(int(ttl_seconds))
        return str(key)

    overwrite = save

    @classmethod
    def load(
        cls,
        value: str | RedisKey,
        step_number: int | None = None,
        *,
        require: bool = True,
    ) -> "InProcess | None":
        if step_number is None:
            key = value if isinstance(value, RedisKey) else RedisKey(str(value))
        else:
            key = cls.key_for_step(str(value), step_number)

        raw = key.hgetall()
        if not raw:
            if require:
                raise RuntimeError(f"Redis hash record missing: {key}")
            return None
        return cls.load_redis(raw)


__all__ = ["DEFAULT_IN_PROCESS_TTL_SECONDS", "InProcess"]
