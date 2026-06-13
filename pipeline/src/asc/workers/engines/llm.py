from __future__ import annotations

from typing import Any, Callable


class LLMEngineUnavailable(RuntimeError):
    pass


def make_call(*, args: dict[str, Any]) -> Callable[[str], str]:
    raise LLMEngineUnavailable("LLM worker engine is not implemented in this bundle")


def should_retry(exc: BaseException) -> bool:
    return not isinstance(exc, LLMEngineUnavailable)


__all__ = ["LLMEngineUnavailable", "make_call", "should_retry"]
