from typing import Any, Protocol


class EngineRun(Protocol):
    def __call__(self, content: str) -> object: ...


def load_engine_run(engine_name: str, *, args: dict[str, Any]) -> EngineRun:
    """Load a worker engine run callable.

    The worker boundary runs engines. It does not assume that every successful
    engine run is an LLM Response. Engines return first-class process result
    models such as Response, Transform, Retrieval, or Failure.

    DEBT: move engine-name compatibility and adapter registry into
    asc.registries once the current pipeline stabilizes.
    """

    normalized = engine_name.strip()
    if normalized.startswith("engines."):
        normalized = normalized.split(".", 1)[1]
    if not normalized:
        raise ValueError("engine name must be non-empty")

    if normalized == "scripts":
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


__all__ = ["EngineRun", "load_engine_run"]
