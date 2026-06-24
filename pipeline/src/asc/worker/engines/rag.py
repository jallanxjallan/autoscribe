from typing import Any, Callable

from asc.models.process.result import Failure, Retrieval

ENGINE = "rag"
ENGINE_COMPONENT = {
    "label": "RAG retrieval",
    "kind": "rag",
    "step_fields": ["collection", "query", "top_k", "instructions"],
}


class RAGEngineUnavailable(RuntimeError):
    pass


def make_run(*, args: dict[str, Any]) -> Callable[[str], Retrieval | Failure]:
    """Return a future RAG run callable.

    This is a deliberate stub. A successful RAG run should return Retrieval,
    not Response. The later LLM step that consumes the retrieval and writes
    prose is what produces a Response.
    """
    raise RAGEngineUnavailable("RAG worker engine is not implemented in this bundle")


def should_retry(exc: BaseException) -> bool:
    return not isinstance(exc, RAGEngineUnavailable)


__all__ = ["ENGINE", "ENGINE_COMPONENT", "RAGEngineUnavailable", "make_run", "should_retry"]
