from __future__ import annotations

from typing import Any, Callable


class RAGEngineUnavailable(RuntimeError):
    pass


def make_call(*, args: dict[str, Any]) -> Callable[[str], str]:
    raise RAGEngineUnavailable("RAG worker engine is not implemented in this bundle")


def should_retry(exc: BaseException) -> bool:
    return not isinstance(exc, RAGEngineUnavailable)


__all__ = ["RAGEngineUnavailable", "make_call", "should_retry"]
