from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from asc.core.timestamp import timestamp
from asc.redis.index_base import FixedRedisIndex


ORCHESTRATOR_QUEUE_KEY = "queue:orchestrator:pending"


@dataclass(frozen=True, slots=True)
class QueuedCall:
    """One call identity claimed by Orchestrator."""

    call_identity: str
    score: float

    @property
    def identity(self) -> str:
        return self.call_identity


def _require_call_identity(value: object, *, field_name: str = "call_identity") -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")

    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} must be non-empty")
    if ":" in text:
        raise ValueError(
            f"{field_name} must be a bare call identity, not a Redis key: {text!r}"
        )
    return text


class OrchestratorQueue(FixedRedisIndex):
    """Pending call queue polled by Orchestrator.

    Members are bare runtime call identities. Orchestrator loads
    CallState.load(identity), then owns call materialization and progression.
    """

    KEY = ORCHESTRATOR_QUEUE_KEY

    def enqueue(self, call_identity: str, *, score: float | None = None) -> int:
        member = _require_call_identity(call_identity)
        normalized_score = timestamp() if score is None else float(score)
        return self.key.zadd({member: normalized_score})

    def enqueue_batch(
        self,
        call_identities: Sequence[str],
        *,
        start_score: float | None = None,
        step: float = 0.001,
    ) -> int:
        if step <= 0:
            raise ValueError("step must be > 0")
        if not call_identities:
            return 0

        score = timestamp() if start_score is None else float(start_score)
        mapping: dict[str, float] = {}
        for index, call_identity in enumerate(call_identities):
            mapping[
                _require_call_identity(
                    call_identity,
                    field_name=f"call_identities[{index}]",
                )
            ] = score
            score += float(step)
        return self.key.zadd(mapping)

    def claim_next(self) -> QueuedCall | None:
        items = self.key.zpopmin(1)
        if not items:
            return None
        member, score = items[0]
        return QueuedCall(call_identity=str(member), score=float(score))

    def claim_call(self) -> str | None:
        claimed = self.claim_next()
        if claimed is None:
            return None
        return claimed.call_identity

    def peek_next(self) -> str | None:
        items = self.key.zrange(0, 0)
        if not items:
            return None
        return str(items[0])

    def count(self) -> int:
        return int(self.key.zcard())

    def clear(self) -> int:
        return int(self.delete())


_QUEUE = OrchestratorQueue()


def orchestrator_queue_key() -> str:
    return ORCHESTRATOR_QUEUE_KEY


def enqueue_call(call_identity: str, *, score: float | None = None) -> int:
    return _QUEUE.enqueue(call_identity, score=score)


def enqueue(call_identity: str, *, score: float | None = None) -> int:
    return enqueue_call(call_identity, score=score)


def enqueue_batch(
    call_identities: Sequence[str],
    *,
    start_score: float | None = None,
    step: float = 0.001,
) -> int:
    return _QUEUE.enqueue_batch(
        call_identities,
        start_score=start_score,
        step=step,
    )


def claim_next() -> QueuedCall | None:
    return _QUEUE.claim_next()


def claim_call() -> str | None:
    return _QUEUE.claim_call()


def peek_next() -> str | None:
    return _QUEUE.peek_next()


def peek_call() -> str | None:
    return peek_next()


def count() -> int:
    return _QUEUE.count()


def clear() -> int:
    return _QUEUE.clear()


__all__ = [
    "ORCHESTRATOR_QUEUE_KEY",
    "OrchestratorQueue",
    "QueuedCall",
    "claim_call",
    "claim_next",
    "clear",
    "count",
    "enqueue",
    "enqueue_batch",
    "enqueue_call",
    "orchestrator_queue_key",
    "peek_call",
    "peek_next",
]
