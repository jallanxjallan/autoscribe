"""Trusted canonical Git plan record. Runtime identities belong elsewhere."""

from typing import Any
import re

from dataclasses import asdict, dataclass

INSTRUCTION_PATTERN = re.compile(r"(?:rol|ctx|spc)_[0-9A-HJKMNP-TV-Z]{16}")
SCOPES = {"rol": "role", "ctx": "context", "spc": "task"}


def instruction_scope(identity: str) -> str:
    if not isinstance(identity, str) or not INSTRUCTION_PATTERN.fullmatch(identity):
        raise ValueError(f"invalid instruction identity: {identity!r}")
    return SCOPES[identity[:3]]


@dataclass(frozen=True, slots=True)
class Plan:
    slug: str
    title: str
    description: str
    steps: dict[str, dict[str, Any]]
    capabilities: dict[str, dict[str, dict[str, Any]]]
    scope: str | None = None

    @property
    def identity(self) -> str:
        return self.slug

    @property
    def total_steps(self) -> int:
        return len(self.steps)

    def step_definition(self, step_number: int) -> dict[str, Any]:
        return dict(self.steps[str(step_number)])

    def step_args(self, step_number: int) -> dict[str, Any]:
        return dict(self.step_definition(step_number)["args"])

    def step_engine(self, step_number: int) -> str:
        return self.step_definition(step_number)["engine"]

    def plan_dict(self) -> dict[str, Any]:
        return asdict(self)
