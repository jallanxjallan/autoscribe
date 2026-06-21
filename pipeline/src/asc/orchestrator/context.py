"""Runtime context passed to orchestrator handlers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class Store(Protocol):
    def load_cursor_for_identity(self, identity: str) -> Any: ...
    def load_plan(self, key: str) -> Any: ...
    def result_key_for_step(self, *, identity: str, step_number: int) -> str: ...
    def input_key_for_step(self, *, identity: str, step_number: int) -> str: ...
    def load_failure(self, key: str) -> Any: ...
    def save_task(self, task: Any) -> str: ...


class Inbox(Protocol):
    def post(self, key: str) -> str: ...


@dataclass(frozen=True, slots=True)
class OrchestratorContext:
    store: Store
    worker_inbox: Inbox
    scrivener_inbox: Inbox


__all__ = ["Inbox", "OrchestratorContext", "Store"]
