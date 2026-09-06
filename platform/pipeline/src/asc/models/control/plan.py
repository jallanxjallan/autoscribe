"""Trusted canonical Git plan record. Runtime identities belong elsewhere."""

from dataclasses import asdict, dataclass
import re
from typing import Any

INSTRUCTION_PATTERN = re.compile(r"(?:rol|ctx|tsk)_[0-9A-HJKMNP-TV-Z]{16}")
SCOPES = {"rol": "role", "ctx": "context", "tsk": "task"}


def instruction_scope(identity: str, *, published: bool = False) -> str:
    if (
        published
        and isinstance(identity, str)
        and re.fullmatch(r"(?:rol|ctx|tsk)\.[a-z0-9-]+\.[a-z0-9]+", identity)
    ):
        return SCOPES[identity[:3]]
    if not isinstance(identity, str) or not INSTRUCTION_PATTERN.fullmatch(identity):
        raise ValueError(f"invalid instruction identity: {identity!r}")
    return SCOPES[identity[:3]]


@dataclass(frozen=True, slots=True)
class Plan:
    """Canonical plan authored by the trusted Control producer."""

    identity: str
    title: str
    description: str
    steps: dict[str, dict[str, Any]]
    capabilities: dict[str, dict[str, dict[str, Any]]]
    scope: str | None = None

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "Plan":
        return cls(**record)

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
