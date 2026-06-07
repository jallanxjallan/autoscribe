from __future__ import annotations

from asc.state.chronology_index import ChronologyIndex, IndexedMember as IndexedCall


CALL_INDEX_KEY = "index:runtime-call:all"


class CallIndex(ChronologyIndex):
    KEY = CALL_INDEX_KEY


_INDEX = CallIndex()


def call_index_key() -> str:
    return CALL_INDEX_KEY


def append(call_identity: str, *, score: float | None = None) -> int:
    return _INDEX.append(call_identity, score=score)


def score(call_identity: str) -> float | None:
    return _INDEX.score(call_identity)


def latest() -> str | None:
    return _INDEX.latest()


def list_identities(start: int = 0, end: int = -1, *, newest_first: bool = False) -> list[str]:
    return _INDEX.list_members(start, end, newest_first=newest_first)


def list_window(*, min_score: float, max_score: float, newest_first: bool = False, limit: int | None = None) -> list[IndexedCall]:
    return _INDEX.list_window(min_score=min_score, max_score=max_score, newest_first=newest_first, limit=limit)


def count() -> int:
    return _INDEX.count()


def clear() -> int:
    return _INDEX.clear()


__all__ = ["CALL_INDEX_KEY", "IndexedCall", "CallIndex", "append", "clear", "count", "latest", "list_identities", "list_window", "call_index_key", "score"]
