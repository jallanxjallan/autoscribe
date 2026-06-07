from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from asc.registries.extensions import load_engine_call


class EngineCall(Protocol):
    def __call__(
        self,
        *,
        prompt: str,
        instructions: list[Any] | None = None,
        step_args: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class RegisteredEngine:
    """Thin wrapper around a runtime engine make_call callable."""

    component: str
    engine_call: EngineCall

    def make_call(
        self,
        *,
        prompt: str,
        instructions: list[Any] | None = None,
        step_args: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.engine_call(
            prompt=prompt,
            instructions=list(instructions or []),
            step_args=dict(step_args or {}),
        )


def build_engine(component: str) -> RegisteredEngine:
    clean_component = component.strip()
    if not clean_component:
        raise ValueError("engine component cannot be empty")

    return RegisteredEngine(
        component=clean_component,
        engine_call=load_engine_call(clean_component),
    )


__all__ = ["EngineCall", "RegisteredEngine", "build_engine"]
