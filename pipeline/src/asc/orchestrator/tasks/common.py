"""Shared orchestration task mechanics.

This module is deliberately queue-neutral.  It owns only the boring contract
work that every task owner needs: required text validation, Redis key shape,
task loading, cursor keys, task numbers, and route decisions.

Queue-specific task construction belongs in sibling modules such as
``worker.py`` and ``scrivener.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypeAlias

from asc.redis.key import RedisKey

try:  # current consolidated import shape
    from asc.models.process.task import ScrivenerTask, WorkerTask
except ImportError:  # transitional split-model import shape
    from asc.models.process.scrivener_task import ScrivenerTask
    from asc.models.process.worker_task import WorkerTask

TaskModel: TypeAlias = WorkerTask | ScrivenerTask


TASK_MODEL_BY_KIND = {
    WorkerTask.kind: WorkerTask,
    ScrivenerTask.kind: ScrivenerTask,
}

TASK_KIND_BY_QUEUE = {
    "worker": WorkerTask.kind,
    "scrivener": ScrivenerTask.kind,
}


@dataclass(frozen=True, slots=True)
class RouteDecision:
    queue_name: str | None
    task: TaskModel | None
    reason: str


def required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} must be non-empty")
    return text


def key_kind(key: str) -> str:
    return RedisKey(required_text(key, "key")).kind


def is_cursor_key(key: str) -> bool:
    return key_kind(key) == "cursor"


def cursor_key_for(cursor: Any) -> str:
    for attr in ("key", "cursor_key"):
        value = getattr(cursor, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()

    identity = required_text(getattr(cursor, "identity", None), "cursor.identity")
    return str(RedisKey.from_parts("cursor", identity, "index"))


def task_number_for(task: Any) -> int:
    value = getattr(task, "task_number", None)
    if value is None:
        value = getattr(task, "step_number", None)
    if value is None:
        raise ValueError("task.task_number is required")
    number = int(value)
    if number < 0:
        raise ValueError("task.task_number must be >= 0")
    return number


def task_key_for(task: TaskModel) -> str:
    return str(RedisKey.from_parts(task.kind, required_text(task.identity, "task.identity")))


# Backward-compatible name used by service.py.
runtime_task_key_for = task_key_for


def load_task(task_key: str) -> TaskModel:
    kind = key_kind(task_key)
    try:
        model_class = TASK_MODEL_BY_KIND[kind]
    except KeyError as exc:
        expected = ", ".join(sorted(TASK_MODEL_BY_KIND))
        raise ValueError(f"unknown task key kind {kind!r}; expected one of: {expected}") from exc

    # Prefer the model's Redis loader.  This keeps Redis access behind the
    # model layer and avoids direct redis-client reads in the orchestrator.
    load = getattr(model_class, "load", None)
    if not callable(load):
        raise TypeError(f"{model_class.__name__} has no load() classmethod")
    return load(task_key)


def assert_task_key_for_queue(*, queue_name: str | None, task_key: str) -> str:
    if queue_name is None:
        return task_key
    if queue_name == "orchestrator":
        if is_cursor_key(task_key) or key_kind(task_key) in TASK_MODEL_BY_KIND:
            return task_key
        raise ValueError(f"orchestrator queue cannot receive key: {task_key}")

    expected_kind = TASK_KIND_BY_QUEUE.get(queue_name)
    if expected_kind is None:
        raise ValueError(f"unknown queue route: {queue_name!r}")

    actual_kind = key_kind(task_key)
    if actual_kind != expected_kind:
        raise ValueError(
            f"{queue_name} queue expected {expected_kind!r} key, got {actual_kind!r}: {task_key}"
        )
    return task_key


__all__ = [
    "RouteDecision",
    "ScrivenerTask",
    "TaskModel",
    "WorkerTask",
    "assert_task_key_for_queue",
    "cursor_key_for",
    "is_cursor_key",
    "key_kind",
    "load_task",
    "required_text",
    "runtime_task_key_for",
    "task_key_for",
    "task_number_for",
]
