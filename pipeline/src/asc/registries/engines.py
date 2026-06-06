from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from asc.models.control.driver import DriverRecord
from asc.models.control.instruction import InstructionRecord
from asc.registries.extensions import load_engine_call


class EngineCall(Protocol):
    def __call__(
        self,
        *,
        prompt: str,
        driver: DriverRecord,
        instructions: list[InstructionRecord],
    ) -> dict[str, Any]: ...


class CallEngine(Protocol):
    def make_call(
        self,
        *,
        prompt: str,
        instructions: list[InstructionRecord],
        step_args: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class RegisteredEngine:
    driver: DriverRecord
    engine_call: EngineCall

    def make_call(
        self,
        *,
        prompt: str,
        instructions: list[InstructionRecord],
        step_args: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        driver = self.driver

        if step_args:
            driver = self.driver.model_copy(
                update={"args": {**dict(self.driver.args), **step_args}}
            )

        return self.engine_call(
            prompt=prompt,
            driver=driver,
            instructions=instructions,
        )


def build_engine(*, driver: DriverRecord) -> CallEngine:
    return RegisteredEngine(
        driver=driver,
        engine_call=load_engine_call(driver.client),
    )


__all__ = ["CallEngine", "RegisteredEngine", "build_engine"]
