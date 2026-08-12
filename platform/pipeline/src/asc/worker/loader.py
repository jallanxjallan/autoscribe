"""Worker runtime extension loader."""

from __future__ import annotations

from typing import Callable

from asc.extensions import load_runtime_call
from asc.models.process.result import Failure, Response, Retrieval, Transform
from asc.models.process.runtime import Runtime
from asc.worker.runtime_io import EngineInput


EngineArtifact = Response | Transform | Retrieval | Failure
EngineCall = Callable[[EngineInput], EngineArtifact]


def load_engine_call(runtime: Runtime) -> EngineCall:
    """Load the executable callable directly from the extensions folder."""
    return load_runtime_call(runtime)


__all__ = ["EngineArtifact", "EngineCall", "load_engine_call"]
