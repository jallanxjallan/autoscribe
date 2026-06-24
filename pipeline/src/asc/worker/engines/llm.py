from typing import Any, Callable

from asc.models.process.result import Failure, Response

ENGINE = "llm"
ENGINE_COMPONENT = {
    "label": "LLM",
    "kind": "llm",
    "step_fields": ["model", "instructions", "temperature", "max_tokens"],
}


class LLMEngineUnavailable(RuntimeError):
    pass


def make_run(*, args: dict[str, Any]) -> Callable[[str], Response | Failure]:
    raise LLMEngineUnavailable("LLM worker engine is not implemented in this bundle")


def should_retry(exc: BaseException) -> bool:
    return not isinstance(exc, LLMEngineUnavailable)


__all__ = ["ENGINE", "ENGINE_COMPONENT", "LLMEngineUnavailable", "make_run", "should_retry"]
