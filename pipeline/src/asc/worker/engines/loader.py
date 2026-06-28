from typing import Any, Protocol


class EngineRun(Protocol):
    def __call__(self, content: str) -> object: ...


_ENGINE_ALIASES = {
    "chatgpt": "llm",
    "gpt": "llm",
    "openai": "llm",
    "llm": "llm",
    "rag": "rag",
    "retrieval": "rag",
    "script": "script",
    "scripts": "script",
    "transform": "script",
}


def normalize_engine_kind(engine_name: object) -> str:
    """Return the canonical worker engine kind.

    Plan/registry values may arrive as friendly names (``chatgpt``), canonical
    kinds (``llm``), or import-style component names (``engines.scripts``).
    Normalize that compatibility at the worker boundary.
    """

    normalized = str(engine_name).strip().lower()
    if normalized.startswith("engines."):
        normalized = normalized.split(".", 1)[1]

    return _ENGINE_ALIASES.get(normalized, normalized)


def load_engine_run(engine_name: str, *, args: dict[str, Any]) -> EngineRun:
    """Load a worker engine run callable.

    Engines return raw payloads. The worker executor owns task/step custody and
    wraps successful payloads into Response, Transform, Retrieval, or Failure.
    """

    normalized = normalize_engine_kind(engine_name)
    if not normalized:
        raise ValueError("engine name must be non-empty")

    if normalized == "script":
        from asc.worker.engines.scripts import make_run
    elif normalized == "llm":
        from asc.worker.engines.llm import make_run
    elif normalized == "rag":
        from asc.worker.engines.rag import make_run
    else:
        raise ValueError(f"unknown worker engine: {engine_name!r}")

    run = make_run(args=args)
    if not callable(run):
        raise TypeError(f"engine {engine_name!r} make_run(...) did not return a callable")
    return run


__all__ = ["EngineRun", "load_engine_run", "normalize_engine_kind"]
