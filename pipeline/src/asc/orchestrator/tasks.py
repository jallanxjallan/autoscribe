"""Orchestrator task dispatcher.

This module deliberately does not know how to construct worker or scrivener
work.  It owns only the queue-token contract and lazily delegates task
construction to the package that will execute the task.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from asc.models.process.loader import load_key
from asc.models.process.task import ScrivenerTask, WorkerTask

from .errors import OrchestratorContractError


@dataclass(frozen=True, slots=True)
class RouteDecision:
    queue_name: str | None
    task: WorkerTask | ScrivenerTask | None
    reason: str


# ---------------------------------------------------------------------------
# Small queue-token contract
# ---------------------------------------------------------------------------


def required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise OrchestratorContractError(f"{field_name} must be a string")
    text = value.strip()
    if not text:
        raise OrchestratorContractError(f"{field_name} must be non-empty")
    return text


def required_key(value: object, field_name: str) -> str:
    if value is None:
        raise OrchestratorContractError(f"{field_name} must be non-empty")
    text = str(value).strip()
    if not text:
        raise OrchestratorContractError(f"{field_name} must be non-empty")
    return text


def is_cursor_key(key: str) -> bool:
    """Return True when a queue token is a fresh cursor handoff."""

    text = required_text(key, "cursor_key")
    return text.startswith("cursor:") or text.endswith(":cursor")


def cursor_key_for(cursor: Any) -> str:
    for attr in ("key", "cursor_key"):
        value = getattr(cursor, attr, None)
        if isinstance(value, str) and value.strip() and is_cursor_key(value.strip()):
            return value.strip()

    identity = required_text(getattr(cursor, "identity", None), "cursor.identity")
    return f"cursor:{identity}:index"


def task_number_for(task: Any) -> int:
    value = getattr(task, "task_number", None)
    if value is None:
        raise OrchestratorContractError("task.task_number is required")
    return int(value)


def load_task(task_key: str) -> WorkerTask | ScrivenerTask:
    key = required_text(task_key, "task_key")
    task = load_key(key)
    if isinstance(task, (WorkerTask, ScrivenerTask)):
        return task
    raise OrchestratorContractError(
        f"orchestrator expected runtime task key, got {type(task).__name__}: {key}"
    )


def runtime_task_key_for(task: WorkerTask | ScrivenerTask) -> str:
    """Return the Redis key for a runtime task without trusting save() output."""

    identity = required_text(getattr(task, "identity", None), "task.identity")
    kind = required_text(getattr(task, "kind", None), "task.kind")

    key_for_identity = getattr(task, "key_for_identity", None)
    if callable(key_for_identity):
        try:
            return required_key(key_for_identity(identity), "task.key_for_identity(identity)")
        except TypeError:
            return required_key(key_for_identity(), "task.key_for_identity()")

    return f"{kind}:{identity}"


def task_key_has_kind(key: str, kind: object) -> bool:
    expected = required_text(kind, "task.kind")
    return required_text(key, "task_key").split(":", 1)[0] == expected


def assert_task_key_for_queue(*, queue_name: str | None, task_key: str) -> str:
    key = required_text(task_key, f"{queue_name}.task_key")

    if queue_name == "worker":
        if not task_key_has_kind(key, WorkerTask.kind):
            raise OrchestratorContractError(f"worker queue requires worker task key, got: {key}")
        return key

    if queue_name == "scrivener":
        if not task_key_has_kind(key, ScrivenerTask.kind):
            raise OrchestratorContractError(f"scrivener queue requires scrivener task key, got: {key}")
        return key

    if queue_name == "orchestrator":
        if is_cursor_key(key) or task_key_has_kind(key, WorkerTask.kind) or task_key_has_kind(key, ScrivenerTask.kind):
            return key
        raise OrchestratorContractError(f"orchestrator queue received unknown key: {key}")

    raise OrchestratorContractError(f"unknown queue name: {queue_name!r}")


# ---------------------------------------------------------------------------
# Lazy dispatch into owning packages
# ---------------------------------------------------------------------------


def plan_step_count(plan: Any) -> int:
    from asc.workers.tasks import plan_step_count as _plan_step_count

    return _plan_step_count(plan)


def make_worker_task(*, cursor: Any, plan: Any, step_number: int, input_key: str | None = None) -> WorkerTask:
    from asc.workers.tasks import make_task

    return make_task(cursor=cursor, plan=plan, step_number=step_number, input_key=input_key)


def make_scrivener_call_task(cursor: Any) -> ScrivenerTask:
    from asc.scrivener.tasks import make_call_task

    return make_call_task(cursor)


def make_scrivener_step_task(*, cursor: Any, worker_task: WorkerTask) -> ScrivenerTask:
    from asc.scrivener.tasks import make_step_task

    return make_step_task(cursor=cursor, worker_task=worker_task)


def make_scrivener_result_task(*, cursor: Any, previous_task: ScrivenerTask) -> ScrivenerTask:
    from asc.scrivener.tasks import make_result_task

    return make_result_task(cursor=cursor, previous_task=previous_task)


__all__ = [
    "RouteDecision",
    "assert_task_key_for_queue",
    "cursor_key_for",
    "is_cursor_key",
    "load_task",
    "make_scrivener_call_task",
    "make_scrivener_result_task",
    "make_scrivener_step_task",
    "make_worker_task",
    "plan_step_count",
    "required_key",
    "required_text",
    "runtime_task_key_for",
    "task_key_has_kind",
    "task_number_for",
]
