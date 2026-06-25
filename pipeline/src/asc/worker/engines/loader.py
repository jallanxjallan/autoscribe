from typing import Any, Protocol


class EngineRun(Protocol):
    def __call__(self, content: str) -> object: ...


def load_engine_run(engine_name: str, *, args: dict[str, Any]) -> EngineRun:
    """Load a worker engine run callable.

    The worker boundary supplies the flattened Step fields as ``args``. Engines
    may cherry-pick the fields they need and ignore the rest.

    Engines should return raw engine payloads, not process result envelopes. The
    worker executor owns task/step custody context and wraps successful payloads
    into Response, Transform, Retrieval, or Failure records.

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
