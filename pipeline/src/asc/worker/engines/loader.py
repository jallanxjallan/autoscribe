from typing import Any, Protocol


class EngineCall(Protocol):
    def __call__(self, content: str) -> object: ...


def load_engine_call(engine_name: str, *, args: dict[str, Any]) -> EngineCall:
    """Load the worker engine adapter for the local-script smoke-test scope.

    LLM/RAG adapter routing is intentionally out of path until the local-script
    worker path is green end-to-end.

    DEBT: move engine-name compatibility and adapter registry into
    asc.registries once the current pipeline stabilizes.
    """

    normalized = engine_name.strip()
    if normalized.startswith("engines."):
        normalized = normalized.split(".", 1)[1]
    if not normalized:
        raise ValueError("engine name must be non-empty")

    if normalized != "scripts":
        raise ValueError(
            f"worker engine {engine_name!r} is outside the local-script smoke-test scope"
        )

    from asc.worker.engines.scripts import make_call

    call = make_call(args=args)
    if not callable(call):
        raise TypeError(f"engine {engine_name!r} make_call(...) did not return a callable")
    return call


__all__ = ["EngineCall", "load_engine_call"]
