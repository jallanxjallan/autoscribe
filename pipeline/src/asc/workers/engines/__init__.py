from __future__ import annotations

import importlib
from typing import Any, Protocol


class EngineCall(Protocol):
    def __call__(self, content: str) -> str: ...


def load_engine_call(engine_name: str, *, args: dict[str, Any]) -> EngineCall:
    """Load a worker-local engine adapter.

    Accepts either ``scripts`` or ``engines.scripts`` while plans migrate away
    from the old extensions engine namespace.
    """

    normalized = engine_name.strip()
    if normalized.startswith("engines."):
        normalized = normalized.split(".", 1)[1]
    if not normalized:
        raise ValueError("engine name must be non-empty")

    module = importlib.import_module(f"asc.workers.engines.{normalized}")
    make_call = getattr(module, "make_call")
    call = make_call(args=args)
    if not callable(call):
        raise TypeError(f"engine {engine_name!r} make_call(...) did not return a callable")
    return call


__all__ = ["EngineCall", "load_engine_call"]
