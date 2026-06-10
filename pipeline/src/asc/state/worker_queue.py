from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from asc.core.timestamp import timestamp
from asc.redis.index_base import FixedRedisIndex
from asc.redis.key import RedisKey


WORKER_QUEUE_KEY = "queue:worker:pending"


@dataclass(frozen=True, slots=True)
class QueuedStep:
    """One concrete runtime step key claimed by a worker."""

    step_key: str
    score: float

    @property
    def identity(self) -> str:
        return self.step_key


def _require_step_key(value: object, *, field_name: str = "step_key") -> str:
    if isinstance(value, RedisKey):
        text = str(value)
    elif isinstance(value, str):
        text = value.strip()
    else:
        raise TypeError(f"{field_name} must be a runtime step Redis key string")

    if not text:
        raise ValueError(f"{field_name} must be non-empty")

    RedisKey(text)
    parts = text.split(":")
    if len(parts) != 3 or parts[0] != "runtime" or not parts[2].startswith("step."):
        raise ValueError(
            f"{field_name} must look like runtime:<identity>:step.<n>; got {text!r}"
        )

    suffix = parts[2].removeprefix("step.")
    if not suffix.isdigit() or int(suffix) < 1:
        raise ValueError(
            f"{field_name} must end with a positive step number; got {text!r}"
        )

    return text


class WorkerQueue(FixedRedisIndex):
    """Pending executable runtime step queue.

    Members are full runtime step keys such as runtime:<identity>:step.1.
    """

    KEY = WORKER_QUEUE_KEY

    def enqueue(self, step_key: str | RedisKey, *, score: float | None = None) -> int:
        member = _require_step_key(step_key)
        normalized_score = timestamp() if score is None else float(score)
        return self.key.zadd({member: normalized_score})

    def enqueue_batch(
        self,
        step_keys: Sequence[str | RedisKey],
        *,
        start_score: float | None = None,
        step: float = 0.001,
    ) -> int:
        if step <= 0:
            raise ValueError("step must be > 0")
        if not step_keys:
            return 0

        score = timestamp() if start_score is None else float(start_score)
        mapping: dict[str, float] = {}
        for index, step_key in enumerate(step_keys):
            mapping[_require_step_key(step_key, field_name=f"step_keys[{index}]")] = score
            score += float(step)
        return self.key.zadd(mapping)

    def claim_next(self) -> QueuedStep | None:
        items = self.key.zpopmin(1)
        if not items:
            return None
        member, score = items[0]
        return QueuedStep(step_key=str(member), score=float(score))

    def claim_step(self) -> str | None:
        claimed = self.claim_next()
        if claimed is None:
            return None
        return claimed.step_key

    def peek_next(self) -> str | None:
        items = self.key.zrange(0, 0)
        if not items:
            return None
        return str(items[0])

    def count(self) -> int:
        return int(self.key.zcard())

    def clear(self) -> int:
        return int(self.delete())


_QUEUE = WorkerQueue()


def worker_queue_key() -> str:
    return WORKER_QUEUE_KEY


def enqueue_step(step_key: str | RedisKey, *, score: float | None = None) -> int:
    return _QUEUE.enqueue(step_key, score=score)


def enqueue(step_key: str | RedisKey, *, score: float | None = None) -> int:
    return enqueue_step(step_key, score=score)


def enqueue_batch(
    step_keys: Sequence[str | RedisKey],
    *,
    start_score: float | None = None,
    step: float = 0.001,
) -> int:
    return _QUEUE.enqueue_batch(step_keys, start_score=start_score, step=step)


def claim_next() -> QueuedStep | None:
    return _QUEUE.claim_next()


def claim_step() -> str | None:
    return _QUEUE.claim_step()


def peek_next() -> str | None:
    return _QUEUE.peek_next()


def peek_step() -> str | None:
    return peek_next()


def count() -> int:
    return _QUEUE.count()


def clear() -> int:
    return _QUEUE.clear()


__all__ = [
    "WORKER_QUEUE_KEY",
    "QueuedStep",
    "WorkerQueue",
    "claim_next",
    "claim_step",
    "clear",
    "count",
    "enqueue",
    "enqueue_batch",
    "enqueue_step",
    "peek_next",
    "peek_step",
    "worker_queue_key",
]
