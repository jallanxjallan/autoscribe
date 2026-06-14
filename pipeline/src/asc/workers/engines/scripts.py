from __future__ import annotations

from typing import Any, Callable

from asc.models.runtime.result import StepFailure, StepResult
from asc.registries.extensions import load_transform

ENGINE = "scripts"
ENGINE_COMPONENT = {
    "label": "Local script",
    "kind": "script",
    "step_fields": ["script", "args", "instructions", "ad_hoc"],
}


class FatalScriptError(RuntimeError):
    """Raised for local script failures; these are not retryable congestion."""


def make_call(*, args: dict[str, Any]) -> Callable[[str], StepResult | StepFailure]:
    script = args["script"]
    transform = load_transform(script)

    def call(content: str) -> StepResult | StepFailure:
        try:
            output = transform(content)
        except Exception as exc:
            return StepFailure(
                content=content,
                failure_reason=type(exc).__name__,
                raw_json={
                    "engine": ENGINE,
                    "script": script,
                    "args": args,
                    "error": str(exc),
                },
            )

        return StepResult(
            content=output,
            raw_json={
                "engine": ENGINE,
                "script": script,
                "args": args,
            },
        )

    return call


def should_retry(exc: BaseException) -> bool:
    return False


__all__ = ["ENGINE", "ENGINE_COMPONENT", "FatalScriptError", "make_call", "should_retry"]