from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EnqueuedCall:
    call: str
    source_identity: str
    cursor_key: str
    call_key: str
    plan_key: str
    results_index_key: str
    cursor_index_key: str
    step_count: int


@dataclass(frozen=True, slots=True)
class EnqueueReport:
    records: tuple[EnqueuedCall, ...]

    @property
    def record_count(self) -> int:
        return len(self.records)

    @property
    def call_count(self) -> int:
        return len(self.records)


__all__ = ["EnqueuedCall", "EnqueueReport"]
