from collections.abc import Sequence

from attr import define

from asc.core.timestamp import timestamp
from asc.redis.index_base import FixedRedisIndex
from asc.redis.key_builder import build_key


STATE_NAMESPACE = "state"
CONTROL_DOMAIN = STATE_NAMESPACE  # compatibility alias
QUEUE_SEGMENT = "queue"
QUEUE_KIND = QUEUE_SEGMENT  # compatibility alias
CALL_IDENTITY = "call-pending"


@define(frozen=True)
class ClaimedCall:
    identity: str
    score: float


def _require_identity(value: object, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    value = value.strip()
    if not value:
        raise ValueError(f"{field_name} must be a non-empty string")
    if ":" in value:
        raise ValueError(f"{field_name} must be a single Redis identity segment")
    return value


class CallQueue(FixedRedisIndex):
    KEY = build_key(STATE_NAMESPACE, CALL_IDENTITY, QUEUE_SEGMENT)

    def enqueue(self, call_identity: str, *, score: float | None = None) -> int:
        call_identity = _require_identity(call_identity, field_name="call_identity")
        normalized_score = timestamp() if score is None else float(score)
        return self.key.zadd({call_identity: normalized_score})

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
        increment = float(step)
        mapping: dict[str, float] = {}

        for index, call_identity in enumerate(call_identities):
            normalized_identity = _require_identity(
                call_identity,
                field_name=f"call_identities[{index}]",
            )
            mapping[normalized_identity] = score
            score += increment

        return self.key.zadd(mapping)

    def claim_next(self) -> ClaimedCall | None:
        items = self.key.zpopmin(1)
        if not items:
            return None

        member, score = items[0]
        return ClaimedCall(identity=member, score=score)

    def peek_next(self) -> str | None:
        items = self.key.zrange(0, 0)
        if not items:
            return None
        return items[0]

    def count(self) -> int:
        return self.key.zcard()

    def clear(self) -> int:
        return self.delete()


_CALL_QUEUE = CallQueue()


def call_queue_key() -> str:
    return CallQueue.KEY


def enqueue_call(call_identity: str, *, score: float | None = None) -> int:
    return _CALL_QUEUE.enqueue(call_identity, score=score)


def enqueue_batch(
    call_identities: Sequence[str],
    *,
    start_score: float | None = None,
    step: float = 0.001,
) -> int:
    return _CALL_QUEUE.enqueue_batch(
        call_identities,
        start_score=start_score,
        step=step,
    )


def claim_next() -> ClaimedCall | None:
    return _CALL_QUEUE.claim_next()


def peek_next() -> str | None:
    return _CALL_QUEUE.peek_next()


def count() -> int:
    return _CALL_QUEUE.count()


def clear() -> int:
    return _CALL_QUEUE.clear()


__all__ = [
    "STATE_NAMESPACE",
    "CONTROL_DOMAIN",
    "QUEUE_SEGMENT",
    "QUEUE_KIND",
    "CALL_IDENTITY",
    "ClaimedCall",
    "CallQueue",
    "call_queue_key",
    "claim_next",
    "clear",
    "count",
    "enqueue_call",
    "enqueue_batch",
    "peek_next",
]
