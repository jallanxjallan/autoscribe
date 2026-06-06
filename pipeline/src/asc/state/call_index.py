from __future__ import annotations

from attr import define

from asc.core.timestamp import timestamp
from asc.redis.index_base import FixedRedisIndex
from asc.redis.key_builder import build_key


STATE_NAMESPACE = "state"
CONTROL_DOMAIN = STATE_NAMESPACE  # compatibility alias
INDEX_SEGMENT = "index"
INDEX_KIND = INDEX_SEGMENT  # compatibility alias
CALL_INDEX_IDENTITY = "call-index"


@define(frozen=True)
class IndexedCall:
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


class CallIndex(FixedRedisIndex):
    """Chronological index of enqueued call identities."""

    KEY = build_key(STATE_NAMESPACE, CALL_INDEX_IDENTITY, INDEX_SEGMENT)

    def append(self, call_identity: str, *, score: float | None = None) -> int:
        call_identity = _require_identity(call_identity, field_name="call_identity")
        normalized_score = timestamp() if score is None else float(score)
        return self.key.zadd({call_identity: normalized_score})

    def score(self, call_identity: str) -> float | None:
        call_identity = _require_identity(call_identity, field_name="call_identity")
        value = self.key.zscore(call_identity)
        if value is None:
            return None
        return float(value)

    def latest(self) -> str | None:
        items = self.key.zrange(-1, -1)
        if not items:
            return None
        return items[0]

    def list_identities(
        self,
        start: int = 0,
        end: int = -1,
        *,
        newest_first: bool = False,
    ) -> list[str]:
        if newest_first:
            return list(self.key.zrevrange(start, end))
        return list(self.key.zrange(start, end))

    def list_window(
        self,
        *,
        min_score: float,
        max_score: float,
        newest_first: bool = False,
        limit: int | None = None,
    ) -> list[IndexedCall]:
        lower = float(min_score)
        upper = float(max_score)

        range_kwargs = {"withscores": True}
        if limit is not None:
            range_kwargs.update({"start": 0, "num": int(limit)})

        if newest_first:
            items = self.key.zrevrangebyscore(
                upper,
                lower,
                **range_kwargs,
            )
        else:
            items = self.key.zrangebyscore(
                lower,
                upper,
                **range_kwargs,
            )

        return [
            IndexedCall(identity=str(identity), score=float(score))
            for identity, score in items
        ]

    def count(self) -> int:
        return self.key.zcard()

    def clear(self) -> int:
        return self.delete()


_CALL_INDEX = CallIndex()


def call_index_key() -> str:
    return CallIndex.KEY


def append(call_identity: str, *, score: float | None = None) -> int:
    return _CALL_INDEX.append(call_identity, score=score)


def score(call_identity: str) -> float | None:
    return _CALL_INDEX.score(call_identity)


def latest() -> str | None:
    return _CALL_INDEX.latest()


def list_identities(
    start: int = 0,
    end: int = -1,
    *,
    newest_first: bool = False,
) -> list[str]:
    return _CALL_INDEX.list_identities(
        start,
        end,
        newest_first=newest_first,
    )


def list_window(
    *,
    min_score: float,
    max_score: float,
    newest_first: bool = False,
    limit: int | None = None,
) -> list[IndexedCall]:
    return _CALL_INDEX.list_window(
        min_score=min_score,
        max_score=max_score,
        newest_first=newest_first,
        limit=limit,
    )


def count() -> int:
    return _CALL_INDEX.count()


def clear() -> int:
    return _CALL_INDEX.clear()


__all__ = [
    "STATE_NAMESPACE",
    "CONTROL_DOMAIN",
    "INDEX_SEGMENT",
    "INDEX_KIND",
    "CALL_INDEX_IDENTITY",
    "IndexedCall",
    "CallIndex",
    "append",
    "clear",
    "count",
    "latest",
    "list_identities",
    "list_window",
    "call_index_key",
    "score",
]
