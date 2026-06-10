from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from asc.core.timestamp import timestamp
from asc.redis.index_base import FixedRedisIndex
from asc.redis.key import RedisKey


CALL_HOLD_QUEUE_KEY = "queue:orchestrator-call:hold"


@dataclass(frozen=True, slots=True)
class QueuedCall:
    """One materialized runtime call waiting for orchestrator custody."""

    call_key: str
    score: float

    @property
    def identity(self) -> str:
        """Compatibility alias for older queue callers."""

        return self.call_key


def _require_call_key(value: object, *, field_name: str = "call_key") -> str:
    if isinstance(value, RedisKey):
        text = str(value)
    elif isinstance(value, str):
        text = value.strip()
    else:
        raise TypeError(f"{field_name} must be a runtime call Redis key string")

    if not text:
        raise ValueError(f"{field_name} must be non-empty")

    key = RedisKey(text)
    if key.namespace != "runtime" or not key.segments or key.segments[-1] != "call":
        raise ValueError(
            f"{field_name} must look like runtime:<identity>:call; got {text!r}"
        )
    return text


class CallHoldQueue(FixedRedisIndex):
    """Materialized call hold queue polled by the orchestrator.

    Enqueue writes full RuntimeCallRecord keys here after it has materialized the
    runtime call, source content, and step definitions. The orchestrator claims
    calls from this queue when active, writes the ledger row, and stages step 1.
    """

    KEY = CALL_HOLD_QUEUE_KEY

    def enqueue(self, call_key: str | RedisKey, *, score: float | None = None) -> int:
        member = _require_call_key(call_key)
        normalized_score = timestamp() if score is None else float(score)
        return self.key.zadd({member: normalized_score})

    def enqueue_batch(
        self,
        call_keys: Sequence[str | RedisKey],
        *,
        start_score: float | None = None,
        step: float = 0.001,
    ) -> int:
        if step <= 0:
            raise ValueError("step must be > 0")
        if not call_keys:
            return 0
        score = timestamp() if start_score is None else float(start_score)
        mapping: dict[str, float] = {}
        for index, call_key in enumerate(call_keys):
            mapping[_require_call_key(call_key, field_name=f"call_keys[{index}]")] = score
            score += float(step)
        return self.key.zadd(mapping)

    def claim_next(self) -> QueuedCall | None:
        items = self.key.zpopmin(1)
        if not items:
            return None
        member, score = items[0]
        return QueuedCall(call_key=str(member), score=float(score))

    def peek_next(self) -> str | None:
        items = self.key.zrange(0, 0)
        if not items:
            return None
        return str(items[0])

    def count(self) -> int:
        return int(self.key.zcard())

    def clear(self) -> int:
        return int(self.delete())


_QUEUE = CallHoldQueue()


def call_hold_queue_key() -> str:
    return CALL_HOLD_QUEUE_KEY


def enqueue(call_key: str | RedisKey, *, score: float | None = None) -> int:
    return _QUEUE.enqueue(call_key, score=score)


def enqueue_call(call_key: str | RedisKey, *, score: float | None = None) -> int:
    return enqueue(call_key, score=score)


def enqueue_batch(
    call_keys: Sequence[str | RedisKey],
    *,
    start_score: float | None = None,
    step: float = 0.001,
) -> int:
    return _QUEUE.enqueue_batch(call_keys, start_score=start_score, step=step)


def claim_next() -> QueuedCall | None:
    return _QUEUE.claim_next()


def claim_call() -> str | None:
    claimed = claim_next()
    if claimed is None:
        return None
    return claimed.call_key


def peek_next() -> str | None:
    return _QUEUE.peek_next()


def peek_call() -> str | None:
    return peek_next()


def count() -> int:
    return _QUEUE.count()


def clear() -> int:
    return _QUEUE.clear()


__all__ = [
    "CALL_HOLD_QUEUE_KEY",
    "CallHoldQueue",
    "QueuedCall",
    "call_hold_queue_key",
    "claim_call",
    "claim_next",
    "clear",
    "count",
    "enqueue",
    "enqueue_batch",
    "enqueue_call",
    "peek_call",
    "peek_next",
]
