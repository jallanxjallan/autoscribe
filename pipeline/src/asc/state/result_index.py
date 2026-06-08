from __future__ import annotations

from asc.redis.key import RedisKey
from asc.state.chronology_index import ChronologyIndex, IndexedMember as IndexedResult


RESULT_INDEX_KEY = "index:runtime-result:all"


class ResultIndex(ChronologyIndex):
    """Chronological index of concrete runtime result Redis keys."""

    KEY = RESULT_INDEX_KEY

    def append_key(self, result_key: str | RedisKey, *, score: float | None = None) -> int:
        RedisKey(str(result_key))
        return self.append(result_key, score=score)

    def key_score(self, result_key: str | RedisKey) -> float | None:
        RedisKey(str(result_key))
        return self.score(result_key)


_INDEX = ResultIndex()


def result_index_key() -> str:
    return RESULT_INDEX_KEY


def append(result_key: str | RedisKey, *, score: float | None = None) -> int:
    return _INDEX.append_key(result_key, score=score)


def score(result_key: str | RedisKey) -> float | None:
    return _INDEX.key_score(result_key)


def latest() -> str | None:
    return _INDEX.latest()


def list_keys(start: int = 0, end: int = -1, *, newest_first: bool = False) -> list[str]:
    return _INDEX.list_members(start, end, newest_first=newest_first)


def list_identities(start: int = 0, end: int = -1, *, newest_first: bool = False) -> list[str]:
    """Compatibility alias.

    Result index members are now full Redis keys, not bare identities.
    """

    return list_keys(start, end, newest_first=newest_first)


def list_window(
    *,
    min_score: float,
    max_score: float,
    newest_first: bool = False,
    limit: int | None = None,
) -> list[IndexedResult]:
    return _INDEX.list_window(
        min_score=min_score,
        max_score=max_score,
        newest_first=newest_first,
        limit=limit,
    )


def count() -> int:
    return _INDEX.count()


def clear() -> int:
    return _INDEX.clear()


__all__ = [
    "RESULT_INDEX_KEY",
    "IndexedResult",
    "ResultIndex",
    "append",
    "clear",
    "count",
    "latest",
    "list_identities",
    "list_keys",
    "list_window",
    "result_index_key",
    "score",
]
