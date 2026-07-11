from __future__ import annotations

from asc.models.control.step import ScriptStep
from asc.models.process.result import Transform
from asc.registries.extensions import load_transform
from asc.worker.runtime_io import EngineInput


ENGINE = "scripts"
ENGINE_COMPONENT = {
    "label": "Local script",
    "kind": "script",
    "step_fields": ["script", "instruction_keys"],
}


def make_call(data: EngineInput) -> Transform:
    """Run one validated local script transform."""

    if not isinstance(data.step, ScriptStep):
        raise TypeError(
            f"{ENGINE} requires ScriptStep, got {type(data.step).__name__}"
        )

    transform = load_transform(data.step.script)
    output = transform(data.content)

    return Transform(
        identity=data.call.identity,
        ordinal=data.step.ordinal,
        content=output,
        raw_json={
            "engine": ENGINE,
            "script": data.step.script,
        },
    )


__all__ = ["ENGINE", "ENGINE_COMPONENT", "make_call"]
