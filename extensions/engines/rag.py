from __future__ import annotations

from asc.models.control.step import RAGStep
from asc.models.process.result import Retrieval
from asc.worker.runtime_io import EngineInput


ENGINE = "rag"
ENGINE_COMPONENT = {
    "label": "RAG",
    "kind": "rag",
    "step_fields": ["rag_profile", "instruction_keys"],
}


def make_call(data: EngineInput) -> Retrieval:
    """Run one validated retrieval step.

    This remains a pass-through placeholder until a concrete RAG provider is
    registered, but it obeys the worker's EngineInput/Result contract.
    """

    if not isinstance(data.step, RAGStep):
        raise TypeError(f"{ENGINE} requires RAGStep, got {type(data.step).__name__}")

    return Retrieval(
        identity=data.call.identity,
        ordinal=data.step.ordinal,
        content=data.content,
        raw_json={
            "engine": ENGINE,
            "rag_profile": data.step.rag_profile,
        },
    )


__all__ = ["ENGINE", "ENGINE_COMPONENT", "make_call"]
