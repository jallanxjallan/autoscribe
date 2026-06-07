from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from asc.core.timestamp import timestamp
from asc.redis.index_base import FixedRedisIndex
from asc.redis.key import RedisKey


RUNTIME_STEP_QUEUE_KEY = "queue:runtime-step:pending"


@dataclass(frozen=True, slots=True)
class QueuedStep:
    """One claimed runtime step queue member."""

    step_key: str
    score: float

    @property
    def identity(self) -> str:
        """Compatibility alias for old callers that expected `.identity`."""

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

    # Validate general Redis key shape. A queued runtime step is deliberately a
    # full key, e.g. runtime:<identity>:step.1, not a single identity segment.
    RedisKey(text)

    parts = text.split(":")
    if len(parts) < 3 or parts[0] != "runtime" or not parts[-1].startswith("step."):
        raise ValueError(
            f"{field_name} must look like runtime:<identity>:step.<n>; got {text!r}"
        )

    return text


class RuntimeStepQueue(FixedRedisIndex):
    """Pending executable runtime step queue.

    Members are full RuntimeStepRecord Redis keys such as:
        runtime:01KTG0QMSZCTC3NNJ2QMG96V33:step.1
    """

    KEY = RUNTIME_STEP_QUEUE_KEY

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

    def peek_next(self) -> str | None:
        items = self.key.zrange(0, 0)
        if not items:
            return None
        return str(items[0])

    def count(self) -> int:
        return int(self.key.zcard())

    def clear(self) -> int:
        return int(self.delete())


_QUEUE = RuntimeStepQueue()


def step_queue_key() -> str:
    return RUNTIME_STEP_QUEUE_KEY


def enqueue_step(step_key: str | RedisKey, *, score: float | None = None) -> int:
    return _QUEUE.enqueue(step_key, score=score)


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
    claimed = claim_next()
    if claimed is None:
        return None
    return claimed.step_key


def peek_next() -> str | None:
    return _QUEUE.peek_next()


def peek_step() -> str | None:
    return peek_next()


def count() -> int:
    return _QUEUE.count()


def clear() -> int:
    return _QUEUE.clear()


__all__ = [
    "RUNTIME_STEP_QUEUE_KEY",
    "QueuedStep",
    "RuntimeStepQueue",
    "claim_next",
    "claim_step",
    "clear",
    "count",
    "enqueue_batch",
    "enqueue_step",
    "peek_next",
    "peek_step",
    "step_queue_key",
]
