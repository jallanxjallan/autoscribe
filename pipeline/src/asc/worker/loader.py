from __future__ import annotations

from typing import Any, Protocol

from asc.registries.extensions import load_engine


class EngineCall(Protocol):
    def __call__(self, *, step: Any, content: Any, task: Any) -> object: ...


def load_engine_call(engine_name: object) -> EngineCall:
    """Load the exact registered extension engine named by the step."""
    module = load_engine(str(engine_name).strip())
    make_call = getattr(module, "make_call")
    if not callable(make_call):
        raise TypeError(f"engine {engine_name!r} make_call is not callable")
    return make_call


__all__ = ["EngineCall", "load_engine_call"]
