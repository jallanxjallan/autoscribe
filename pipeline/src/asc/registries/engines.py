"""Engine registry compatibility helpers.

The live worker path imports ``asc.registries.extensions.load_engine_call``
directly. This module is intentionally thin and keeps only the current runtime
contract: a registered engine callable accepts content, step, and call keyword
arguments and returns an instantiated Result or Failure model.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from asc.models.process.result import Failure, Response, Retrieval, Transform
from asc.registries.extensions import load_engine_call


EngineArtifact = Response | Transform | Retrieval | Failure


class EngineCall(Protocol):
    def __call__(self, *, content: Any, step: Any, call: Any) -> EngineArtifact: ...


@dataclass(frozen=True, slots=True)
class RegisteredEngine:
    component: str
    engine_call: EngineCall

    def make_call(self, *, content: Any, step: Any, call: Any) -> EngineArtifact:
        return self.engine_call(content=content, step=step, call=call)


def build_engine(component: str) -> RegisteredEngine:
    clean_component = component.strip()
    if not clean_component:
        raise ValueError("engine component cannot be empty")

    return RegisteredEngine(
        component=clean_component,
        engine_call=load_engine_call(clean_component),
    )


__all__ = ["EngineArtifact", "EngineCall", "RegisteredEngine", "build_engine"]
