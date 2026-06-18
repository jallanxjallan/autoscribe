"""Outcome helpers for completed daemon tasks.

The orchestrator queue receives task keys after workers and scrivener finish.
These lightweight wrappers make the returned task type explicit without putting
current task state back on the cursor.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    from asc.models.process.task import ScrivenerTask, WorkerTask
except ImportError:
    from asc.models.process.scrivener_task import ScrivenerTask
    from asc.models.process.worker_task import WorkerTask

from .errors import OrchestratorContractError
from .tasks import load_task, required_text, task_number_for


@dataclass(frozen=True, slots=True)
class WorkerOutcome:
    task: WorkerTask

    @classmethod
    def from_key(cls, task_key: str) -> "WorkerOutcome":
        task = load_task(task_key)
        if not isinstance(task, WorkerTask):
            raise OrchestratorContractError(f"expected worker task key, got {type(task).__name__}: {task_key}")
        return cls(task=task)

    @property
    def cursor_key(self) -> str:
        return required_text(getattr(self.task, "cursor_key", None), "worker_outcome.cursor_key")

    @property
    def task_number(self) -> int:
        return task_number_for(self.task)


@dataclass(frozen=True, slots=True)
class ScrivenerOutcome:
    task: ScrivenerTask

    @classmethod
    def from_key(cls, task_key: str) -> "ScrivenerOutcome":
        task = load_task(task_key)
        if not isinstance(task, ScrivenerTask):
            raise OrchestratorContractError(f"expected scrivener task key, got {type(task).__name__}: {task_key}")
        return cls(task=task)

    @property
    def cursor_key(self) -> str:
        return required_text(getattr(self.task, "cursor_key", None), "scrivener_outcome.cursor_key")

    @property
    def action(self) -> str:
        return required_text(getattr(self.task, "action", None), "scrivener_outcome.action")

    @property
    def task_number(self) -> int:
        return task_number_for(self.task)


def outcome_from_key(task_key: str) -> WorkerOutcome | ScrivenerOutcome:
    task = load_task(task_key)
    if isinstance(task, WorkerTask):
        return WorkerOutcome(task=task)
    if isinstance(task, ScrivenerTask):
        return ScrivenerOutcome(task=task)
    raise OrchestratorContractError(f"unsupported outcome task type: {type(task).__name__}")


def is_scrivener_failure(outcome: Any) -> bool:
    return getattr(outcome, "type", "") == "scrivener_failure" or getattr(outcome, "kind", "") in {
        "scrivener_failure",
        "failure",
    }


def is_scrivener_result(outcome: Any) -> bool:
    return getattr(outcome, "type", "") == "scrivener_result" or getattr(outcome, "kind", "") in {
        "scrivener_result",
        "result",
    }


def describe_scrivener_failure(outcome: Any) -> str:
    action = getattr(outcome, "action", "<unknown>")
    reason = getattr(outcome, "failure_reason", "")
    message = getattr(outcome, "fail_message", "")
    if reason and message:
        return f"scrivener {action} failed: {reason}: {message}"
    if message:
        return f"scrivener {action} failed: {message}"
    return f"scrivener {action} failed"


__all__ = [
    "ScrivenerOutcome",
    "WorkerOutcome",
    "describe_scrivener_failure",
    "is_scrivener_failure",
    "is_scrivener_result",
    "outcome_from_key",
]
