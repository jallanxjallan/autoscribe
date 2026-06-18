"""Scrivener task factories.

Scrivener owns ledger-write task shape. The orchestrator should only decide
that a call, step, or result ledger write is next.
"""

from __future__ import annotations

from typing import Any

from asc.models.process.task import ScrivenerTask, WorkerTask
from asc.redis.key import RedisKey


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} must be non-empty")
    return text


def cursor_key_for(cursor: Any) -> str:
    """Return the full Redis key for a runtime cursor."""

    for attr in ("key", "cursor_key"):
        value = getattr(cursor, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()

    identity = _required_text(getattr(cursor, "identity", None), "cursor.identity")
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


def task_identity(call_identity: str, action: str, task_number: int = 0) -> str:
    call_identity = _required_text(call_identity, "call_identity")
    action = _required_text(action, "action")
    if task_number:
        return f"{call_identity}.scrivener.{action}.{int(task_number)}"
    return f"{call_identity}.scrivener.{action}"


def make_call_task(cursor: Any) -> ScrivenerTask:
    identity = _required_text(getattr(cursor, "identity", None), "cursor.identity")
    call_key = _required_text(getattr(cursor, "call_key", None), "cursor.call_key")

    return ScrivenerTask(
        identity=task_identity(identity, "write_call"),
        task_number=0,
        cursor_key=cursor_key_for(cursor),
        action="write_call",
        source_key=call_key,
        ledger_table="calls",
    )


def make_step_task(*, cursor: Any, worker_task: WorkerTask) -> ScrivenerTask:
    identity = _required_text(getattr(cursor, "identity", None), "cursor.identity")
    step_number = task_number_for(worker_task)
    source_key = _required_text(getattr(worker_task, "output_key", None), "worker_task.output_key")

    return ScrivenerTask(
        identity=task_identity(identity, "write_step", step_number),
        task_number=step_number,
        cursor_key=cursor_key_for(cursor),
        action="write_step",
        source_key=source_key,
        ledger_table="steps",
    )


def make_result_task(*, cursor: Any, previous_task: ScrivenerTask) -> ScrivenerTask:
    identity = _required_text(getattr(cursor, "identity", None), "cursor.identity")
    task_number = task_number_for(previous_task)
    source_key = _required_text(getattr(previous_task, "source_key", None), "previous_task.source_key")

    return ScrivenerTask(
        identity=task_identity(identity, "write_result"),
        task_number=task_number,
        cursor_key=cursor_key_for(cursor),
        action="write_result",
        source_key=source_key,
        ledger_table="results",
    )


__all__ = [
    "cursor_key_for",
    "make_call_task",
    "make_result_task",
    "make_step_task",
    "task_identity",
    "task_number_for",
]
