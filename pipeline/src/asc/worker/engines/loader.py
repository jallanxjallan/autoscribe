from typing import Any, Protocol


class EngineRun(Protocol):
    def __call__(self, content: str) -> object: ...


def normalize_engine_kind(engine_name: object) -> str:
    """Return the worker engine kind for a registry or plan engine value.

    Registry snapshots may carry importable component keys such as
    ``engines.scripts`` while worker execution deals in engine kinds such as
    ``script``. Keep that compatibility at the worker boundary until plan
    materialization stores canonical engine kinds directly.
    """

    normalized = str(engine_name).strip().lower()
    if normalized.startswith("engines."):
        normalized = normalized.split(".", 1)[1]

    if normalized == "scripts":
        return "script"

    return normalized


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
