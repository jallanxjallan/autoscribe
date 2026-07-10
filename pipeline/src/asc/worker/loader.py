"""Worker runtime extension loader."""

from __future__ import annotations

from typing import Callable

from asc.models.process.result import Failure, Response, Retrieval, Transform
from asc.registries.extensions import load_engine_call as _load_engine_call
from asc.worker.runtime_io import EngineInput


EngineArtifact = Response | Transform | Retrieval | Failure
EngineCall = Callable[[EngineInput], EngineArtifact]


def load_engine_call(component: str) -> EngineCall:
    """Load the registered engine callable for a Step engine component."""
    clean_component = component.strip()
    if not clean_component:
        raise ValueError("worker engine component cannot be empty")
    return _load_engine_call(clean_component)


__all__ = ["EngineArtifact", "EngineCall", "load_engine_call"]
