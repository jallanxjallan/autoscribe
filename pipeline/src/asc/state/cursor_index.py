from __future__ import annotations

import time
from collections.abc import Iterable
from dataclasses import dataclass
from typing import ClassVar, Literal, overload

from asc.redis.index_base import FixedRedisHashIndex
from asc.redis.key import RedisKey


CURSOR_INDEX_KEY = "control:cursor:index"
ACTIVE_CURSOR_INDEX_KEY = "control:cursor:active"
DEFAULT_STALE_AFTER_SECONDS = 30.0


def _require_text(value: object, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")

    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} must be non-empty")

    return text


def _require_key(value: object, *, field_name: str = "key") -> str:
    text = _require_text(value, field_name=field_name)

    if ":" not in text:
        raise ValueError(f"{field_name} must be a full Redis key, not a bare identity")

    return text


def _redis_text(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")

    if isinstance(value, str):
        return value

    raise TypeError(f"expected Redis text value, got {type(value).__name__}")


class CursorIndex(FixedRedisHashIndex):
    """Global process identity -> active cursor key map."""

    KEY: ClassVar[str] = CURSOR_INDEX_KEY

    def set(self, identity: str, cursor_key: str) -> str:
        normalized_identity = _require_text(identity, field_name="identity")
        normalized_key = _require_key(cursor_key, field_name="cursor_key")

        self.key.hset(field=normalized_identity, value=normalized_key)
        return normalized_key

    @overload
    def get(self, identity: str, *, require: Literal[True]) -> str: ...

    @overload
    def get(self, identity: str, *, require: Literal[False] = False) -> str | None: ...

    def get(self, identity: str, *, require: bool = False) -> str | None:
        normalized_identity = _require_text(identity, field_name="identity")
        value = self.key.hget(normalized_identity)

        if value is None:
            if require:
                raise KeyError(f"cursor not found for identity: {normalized_identity}")
            return None

        return _redis_text(value)

    def delete(self, identity: str) -> int:
        return int(self.key.hdel(_require_text(identity, field_name="identity")))

    def has(self, identity: str) -> bool:
        return self.get(identity) is not None

    def list_cursors(self) -> dict[str, str]:
        entries = self.key.hgetall()
        return {
            _redis_text(identity): _redis_text(cursor_key)
            for identity, cursor_key in sorted(entries.items())
        }

    def clear(self) -> int:
        return int(super().delete())


@dataclass(frozen=True, slots=True)
class ActiveCursor:
    cursor_key: str
    score: float

    @property
    def identity(self) -> str:
        return self.cursor_key

    @property
    def due_at(self) -> float:
        return self.score


class ActiveCursorIndex:
    """Redis ZSET adapter for live cursor supervision.

    This is not a work queue. It records cursors that should exist and uses
    scores as last-seen / check-at metadata for watchdog and recovery logic.
    """

    KEY: ClassVar[str] = ACTIVE_CURSOR_INDEX_KEY
    DEFAULT_STALE_AFTER_SECONDS: ClassVar[float] = DEFAULT_STALE_AFTER_SECONDS

    def __init__(self, key: str | None = None) -> None:
        self.key = RedisKey(key or self.KEY)

    def __str__(self) -> str:
        return str(self.key)

    @staticmethod
    def clean_cursor_key(cursor_key: str) -> str:
        return _require_key(cursor_key, field_name="cursor_key")

    @staticmethod
    def score(score: float | None = None) -> float:
        return float(time.time() if score is None else score)

    def touch(self, cursor_key: str, *, score: float | None = None) -> int:
        return int(self.key.zadd({self.clean_cursor_key(cursor_key): self.score(score)}))

    def schedule(self, cursor_key: str, *, score: float | None = None) -> int:
        return self.touch(cursor_key, score=score)

    def reschedule(self, cursor_key: str, *, delay_seconds: float = 0.0) -> int:
        return self.touch(
            cursor_key,
            score=time.time() + max(0.0, float(delay_seconds)),
        )

    def claim_stale(
        self,
        *,
        now: float | None = None,
        stale_after_seconds: float = DEFAULT_STALE_AFTER_SECONDS,
        lease_seconds: float = DEFAULT_STALE_AFTER_SECONDS,
        limit: int = 100,
    ) -> list[ActiveCursor]:
        if limit <= 0:
            return []

        cutoff = self.score(now) - max(0.0, float(stale_after_seconds))
        rows = self.key.zrangebyscore(
            "-inf",
            cutoff,
            start=0,
            num=int(limit),
            withscores=True,
        )
        if not rows:
            return []

        lease_until = self.score(now) + max(0.0, float(lease_seconds))
        claimed: list[ActiveCursor] = []
        for raw_key, raw_score in rows:
            cursor_key = self.clean_cursor_key(_redis_text(raw_key))
            self.key.zadd({cursor_key: lease_until})
            claimed.append(ActiveCursor(cursor_key=cursor_key, score=float(raw_score)))
        return claimed

    def claim_due(
        self,
        *,
        now: float | None = None,
        limit: int = 100,
    ) -> list[ActiveCursor]:
        return self.claim_stale(now=now, stale_after_seconds=0.0, limit=limit)

    def claim_next(self) -> ActiveCursor | None:
        rows = self.claim_stale(limit=1)
        return rows[0] if rows else None

    def peek_stale(
        self,
        *,
        now: float | None = None,
        stale_after_seconds: float = DEFAULT_STALE_AFTER_SECONDS,
        limit: int = 100,
    ) -> list[ActiveCursor]:
        if limit <= 0:
            return []

        cutoff = self.score(now) - max(0.0, float(stale_after_seconds))
        rows = self.key.zrangebyscore(
            "-inf",
            cutoff,
            start=0,
            num=int(limit),
            withscores=True,
        )
        return [
            ActiveCursor(cursor_key=self.clean_cursor_key(_redis_text(k)), score=float(s))
            for k, s in rows
        ]

    def peek_due(
        self,
        *,
        now: float | None = None,
        limit: int = 100,
    ) -> list[ActiveCursor]:
        return self.peek_stale(now=now, stale_after_seconds=0.0, limit=limit)

    def peek_next(self) -> ActiveCursor | None:
        rows = self.peek_stale(limit=1)
        return rows[0] if rows else None

    def remove(self, cursor_key: str) -> int:
        return int(self.key.zrem(self.clean_cursor_key(cursor_key)))

    def count(self) -> int:
        return int(self.key.zcard())

    def clear(self) -> int:
        return int(self.key.delete())

    def scheduled(self, items: Iterable[str]) -> int:
        now = time.time()
        mapping = {self.clean_cursor_key(item): now for item in items}
        if not mapping:
            return 0
        return int(self.key.zadd(mapping))


_cursor_index = CursorIndex()
active_cursor_index = ActiveCursorIndex()


def set_cursor_key(identity: str, cursor_key: str) -> str:
    return _cursor_index.set(identity, cursor_key)


def get_cursor_key(identity: str, *, require: bool = False) -> str | None:
    return _cursor_index.get(identity, require=require)


def delete_cursor_key(identity: str) -> int:
    return _cursor_index.delete(identity)


def has_cursor_key(identity: str) -> bool:
    return _cursor_index.has(identity)


def list_cursor_keys() -> dict[str, str]:
    return _cursor_index.list_cursors()


def clear_cursor_index() -> int:
    return _cursor_index.clear()


__all__ = [
    "ACTIVE_CURSOR_INDEX_KEY",
    "CURSOR_INDEX_KEY",
    "DEFAULT_STALE_AFTER_SECONDS",
    "ActiveCursor",
    "ActiveCursorIndex",
    "CursorIndex",
    "active_cursor_index",
    "clear_cursor_index",
    "delete_cursor_key",
    "get_cursor_key",
    "has_cursor_key",
    "list_cursor_keys",
    "set_cursor_key",
]
